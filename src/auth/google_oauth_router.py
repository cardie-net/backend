"""Custom Google OAuth router for frontend redirect flow.

The default fastapi-users OAuth router returns JSON from the callback, which
doesn't work when Google redirects the browser there directly. This module
replaces that with a flow that redirects the browser to the frontend with
the JWT token as a URL parameter.
"""

import secrets
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi_users import models
from fastapi_users.authentication import Strategy
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.jwt import decode_jwt, generate_jwt
from fastapi_users.manager import BaseUserManager
from fastapi_users.router.common import ErrorCode
from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from httpx_oauth.oauth2 import OAuth2Token

from ..config import settings
from .backend import auth_backend
from .oauth import google_oauth_client
from .user_manager import UserManager, get_user_manager

STATE_TOKEN_AUDIENCE = "fastapi-users:oauth-state"
CSRF_TOKEN_KEY = "csrftoken"
CSRF_TOKEN_COOKIE_NAME = "fastapiusersoauthcsrf"

CALLBACK_ROUTE_NAME = "oauth:google.jwt.callback"


def _generate_state_token(data: dict[str, str], lifetime_seconds: int = 3600) -> str:
    data["aud"] = STATE_TOKEN_AUDIENCE
    return generate_jwt(data, settings.SECRET_KEY, lifetime_seconds)


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
        user_manager: UserManager = Depends(get_user_manager),
        strategy: Strategy[models.UP, models.ID] = Depends(auth_backend.get_strategy),
    ):
        """Handle Google's OAuth callback and redirect to the frontend with a JWT."""
        token, state = access_token_state

        # Validate state token
        try:
            state_data = decode_jwt(state, settings.SECRET_KEY, [STATE_TOKEN_AUDIENCE])
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

        # Exchange Google token for user info
        account_id, account_email = await google_oauth_client.get_id_email(
            token["access_token"]
        )

        if account_email is None:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_no_email"})
            )

        # Create or retrieve user via fastapi-users' oauth_callback
        try:
            user = await user_manager.oauth_callback(
                google_oauth_client.name,
                token["access_token"],
                account_id,
                account_email,
                token.get("expires_at"),
                token.get("refresh_token"),
                request,
                associate_by_email=True,
                is_verified_by_default=True,
            )
        except UserAlreadyExists:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_user_exists"})
            )

        if not user.is_active:
            return RedirectResponse(
                url=_build_frontend_url("/login", {"error": "oauth_user_inactive"})
            )

        # Generate JWT
        jwt_token = await strategy.write_token(user)

        # Redirect to frontend callback page with the token
        response = RedirectResponse(
            url=_build_frontend_url("/auth/google/callback", {"token": jwt_token})
        )

        # Clean up the CSRF cookie
        response.delete_cookie(
            CSRF_TOKEN_COOKIE_NAME,
            path="/",
        )

        return response

    return router
