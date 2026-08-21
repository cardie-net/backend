"""Custom Google OAuth router for frontend redirect flow.

The default fastapi-users OAuth router returns JSON from the callback, which
doesn't work when Google redirects the browser there directly. This module
replaces that with a flow that redirects the browser to the frontend with
the JWT token as a URL parameter.
"""

import datetime
import logging
import secrets
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from httpx_oauth.oauth2 import OAuth2Token
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import User
from .oauth import google_oauth_client
from .service import handle_oauth_callback
from .utils import COOKIE_NAME, create_access_token, get_optional_current_user

STATE_TOKEN_AUDIENCE = "fastapi-users:oauth-state"
CSRF_TOKEN_KEY = "csrftoken"
CSRF_TOKEN_COOKIE_NAME = "fastapiusersoauthcsrf"

CALLBACK_ROUTE_NAME = "oauth:google.jwt.callback"
logger = logging.getLogger(__name__)


def _generate_state_token(data: dict[str, str], lifetime_seconds: int = 3600) -> str:
    data["aud"] = STATE_TOKEN_AUDIENCE
    data["exp"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=lifetime_seconds
    )
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _build_frontend_url(path: str, params: dict[str, str] | None = None) -> str:
    url = f"{settings.FRONTEND_URL}{path}"
    if params:
        url += f"?{urlencode(params)}"
    return url


def _public_callback_url(request: Request) -> str:
    """The callback URL that Google must redirect the browser to.

    When PUBLIC_BACKEND_URL is set (backend behind a TLS-terminating reverse
    proxy), use it as the scheme/host and only take the path from the request,
    since the backend may otherwise see "http" / an internal host. Otherwise
    fall back to the request-derived URL, which is correct for direct access.
    """
    if settings.PUBLIC_BACKEND_URL:
        path = request.url_for(CALLBACK_ROUTE_NAME).path
        return f"{settings.PUBLIC_BACKEND_URL.rstrip('/')}{path}"
    return str(request.url_for(CALLBACK_ROUTE_NAME))


async def oauth2_authorize_callback(
    request: Request,
    code: str | None = None,
    code_verifier: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> tuple[OAuth2Token, str | None]:
    """Dependency that exchanges the Google authorization code for a token.

    Wraps httpx_oauth's OAuth2AuthorizeCallback with an explicit redirect_url so
    the token exchange uses the same public URL that Google validated during
    authorization (Google re-checks redirect_uri on the token endpoint).
    """
    callback = OAuth2AuthorizeCallback(
        google_oauth_client,
        redirect_url=_public_callback_url(request),
    )
    return await callback(request, code, code_verifier, state, error)


def create_google_oauth_router() -> APIRouter:
    """Create a Google OAuth router with frontend redirect callbacks."""
    router = APIRouter()

    @router.get("/authorize")
    async def authorize(
        request: Request,
        scopes: list[str] = Query(None),
    ) -> RedirectResponse:
        """Redirect the browser directly to Google's consent screen."""
        callback_url = _public_callback_url(request)

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
            secure=settings.COOKIE_SECURE,
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
        guest_user: User | None = Depends(get_optional_current_user),
    ) -> RedirectResponse:
        """Handle Google's OAuth callback and redirect to the frontend with a JWT."""
        token, state = access_token_state

        # Validate state token
        try:
            state_data = jwt.decode(
                state,
                settings.SECRET_KEY,
                audience=STATE_TOKEN_AUDIENCE,
                algorithms=[settings.JWT_ALGORITHM],
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
            logger.error(
                "Google OAuth get_id_email failed. Please ensure the 'Google People API' is enabled in your Google Cloud Console. Details: %s",
                error_text,
            )
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_profile_error"})
            )

        if account_email is None:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_no_email"})
            )

        # Create, upgrade, or retrieve user via service
        try:
            user = await handle_oauth_callback(
                db=db,
                oauth_name=google_oauth_client.name,
                access_token=token["access_token"],
                account_id=account_id,
                account_email=account_email,
                expires_at=token.get("expires_at"),
                refresh_token=token.get("refresh_token"),
                guest_user=guest_user,
            )
        except Exception as e:
            logger.error("OAuth callback failed: %s", e)
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_user_exists"})
            )

        if not user.is_active:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_user_inactive"})
            )

        # Generate JWT
        jwt_token = create_access_token(user.id)

        # Redirect to frontend decks page
        response = RedirectResponse(url=_build_frontend_url("/decks"))

        # Set cookie directly
        response.set_cookie(
            COOKIE_NAME,
            jwt_token,
            max_age=3600 * 24 * 7,
            httponly=True,
            samesite="lax",
            secure=settings.COOKIE_SECURE,
        )

        # Clean up the CSRF cookie
        response.delete_cookie(
            CSRF_TOKEN_COOKIE_NAME,
            path="/",
        )

        return response

    return router
