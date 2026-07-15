"""Custom Google OAuth router for frontend redirect flow.

The default fastapi-users OAuth router returns JSON from the callback, which
doesn't work when Google redirects the browser there directly. This module
replaces that with a flow that redirects the browser to the frontend with
the JWT token as a URL parameter.
"""

import datetime
import secrets
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from httpx_oauth.oauth2 import OAuth2Token
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from .oauth import google_oauth_client
from .service import handle_oauth_callback
from .utils import COOKIE_NAME, create_access_token

STATE_TOKEN_AUDIENCE = "fastapi-users:oauth-state"
CSRF_TOKEN_KEY = "csrftoken"
CSRF_TOKEN_COOKIE_NAME = "fastapiusersoauthcsrf"

CALLBACK_ROUTE_NAME = "oauth:google.jwt.callback"


def _generate_state_token(data: dict[str, str], lifetime_seconds: int = 3600) -> str:
    data["aud"] = STATE_TOKEN_AUDIENCE
    data["exp"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=lifetime_seconds
    )
    return jwt.encode(data, settings.SECRET_KEY, algorithm="HS256")


def _generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _build_frontend_url(path: str, params: dict[str, str] | None = None) -> str:
    url = f"{settings.FRONTEND_URL}{path}"
    if params:
        url += f"?{urlencode(params)}"
    return url


def create_google_oauth_router() -> APIRouter:
    """Create a Google OAuth router with frontend redirect callbacks."""
    router = APIRouter()

    oauth2_authorize_callback = OAuth2AuthorizeCallback(
        google_oauth_client,
        route_name=CALLBACK_ROUTE_NAME,
    )

    @router.get("/authorize")
    async def authorize(
        request: Request,
        scopes: list[str] = Query(None),
    ) -> RedirectResponse:
        """Redirect the browser directly to Google's consent screen."""
        callback_url = str(request.url_for(CALLBACK_ROUTE_NAME))

        csrf_token = _generate_csrf_token()
        state_data: dict[str, str] = {CSRF_TOKEN_KEY: csrf_token}
        state = _generate_state_token(state_data)

        authorization_url = await google_oauth_client.get_authorization_url(
            callback_url,
            state,
            scopes,
        )

        response = RedirectResponse(url=authorization_url)
        response.set_cookie(
            CSRF_TOKEN_COOKIE_NAME,
            csrf_token,
            max_age=3600,
            path="/",
            secure=False,  # Set True in production with HTTPS
            httponly=True,
            samesite="lax",
        )
        return response

    @router.get("/callback", name=CALLBACK_ROUTE_NAME)
    async def callback(
        request: Request,
        access_token_state: tuple[OAuth2Token, str] = Depends(
            oauth2_authorize_callback
        ),
        db: AsyncSession = Depends(get_db),
    ):
        """Handle Google's OAuth callback and redirect to the frontend with a JWT."""
        token, state = access_token_state

        # Validate state token
        try:
            state_data = jwt.decode(
                state,
                settings.SECRET_KEY,
                audience=STATE_TOKEN_AUDIENCE,
                algorithms=["HS256"],
            )
        except jwt.DecodeError:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_invalid_state"})
            )
        except jwt.ExpiredSignatureError:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_state_expired"})
            )

        # Validate CSRF token
        cookie_csrf_token = request.cookies.get(CSRF_TOKEN_COOKIE_NAME)
        state_csrf_token = state_data.get(CSRF_TOKEN_KEY)
        if (
            not cookie_csrf_token
            or not state_csrf_token
            or not secrets.compare_digest(cookie_csrf_token, state_csrf_token)
        ):
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_csrf_mismatch"})
            )

        from httpx_oauth.exceptions import GetIdEmailError

        # Exchange Google token for user info
        try:
            account_id, account_email = await google_oauth_client.get_id_email(
                token["access_token"]
            )
        except GetIdEmailError as e:
            error_text = (
                getattr(e.response, "text", "Unknown")
                if hasattr(e, "response") and e.response
                else str(e)
            )
            print(
                f"Google OAuth get_id_email failed. Please ensure the 'Google People API' is enabled in your Google Cloud Console. Details: {error_text}"
            )
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_profile_error"})
            )

        if account_email is None:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_no_email"})
            )

        # Create or retrieve user via service
        try:
            user = await handle_oauth_callback(
                db=db,
                oauth_name=google_oauth_client.name,
                access_token=token["access_token"],
                account_id=account_id,
                account_email=account_email,
                expires_at=token.get("expires_at"),
                refresh_token=token.get("refresh_token"),
            )
        except Exception as e:
            print(f"OAuth callback failed: {e}")
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_user_exists"})
            )

        if not user.is_active:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_user_inactive"})
            )

        # Generate JWT
        jwt_token = create_access_token(user.id)

        # Redirect to frontend home page
        response = RedirectResponse(url=_build_frontend_url("/"))

        # Set cookie directly
        response.set_cookie(
            COOKIE_NAME,
            jwt_token,
            max_age=3600 * 24 * 7,
            httponly=True,
            samesite="lax",
            secure=False,
        )

        # Clean up the CSRF cookie
        response.delete_cookie(
            CSRF_TOKEN_COOKIE_NAME,
            path="/",
        )

        return response

    return router
