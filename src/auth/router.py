import uuid
from datetime import datetime, timezone

import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..config import settings
from ..database import get_db
from ..models import PendingRegistration, User, UserCreate, UserRead
from .google_oauth_router import create_google_oauth_router
from .service import (
    create_user,
    generate_reset_token,
    promote_guest_by_token,
    reset_password,
    send_forgot_password_email,
    send_verification_email,
    stage_pending_registration,
)
from .utils import (
    COOKIE_NAME,
    create_access_token,
    current_active_user,
    get_optional_current_user,
    get_password_hash,
    verify_password,
)

# Keep the export for other modules that import current_active_user from here
__all__ = ["current_active_user", "create_auth_router"]


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class RequestVerifyEmailRequest(BaseModel):
    email: EmailStr


def create_auth_router() -> APIRouter:
    router = APIRouter()

    # Google OAuth
    router.include_router(
        create_google_oauth_router(),
        prefix="/google",
        tags=["auth"],
    )

    @router.post("/jwt/login", tags=["auth"])
    async def login(
        response: Response,
        credentials: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(get_db),
        guest_user: User | None = Depends(get_optional_current_user),
    ) -> None:
        """Authenticate a user and set a session cookie.

        Everyone starts as a guest; logging into a real account discards the
        guest session and all its data (no merging).
        """
        stmt = select(User).where(User.email == credentials.username)
        user = (await db.execute(stmt)).unique().scalar_one_or_none()

        if not user or user.is_guest:
            raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")
        if not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")

        # A successful login replaces the guest session: discard the guest
        # account (cascading deletes remove its decks, progress, stars, etc.).
        # Note: any pending registration pointing at this guest is discarded
        # with it, matching the "guest data is never merged" rule.
        if guest_user is not None and guest_user.is_guest:
            await db.delete(guest_user)

        user.last_active_at = datetime.now(timezone.utc)
        db.add(user)
        await db.commit()

        access_token = create_access_token(user.id)
        response.status_code = status.HTTP_204_NO_CONTENT
        response.set_cookie(
            COOKIE_NAME,
            access_token,
            max_age=3600 * 24 * 7,
            httponly=True,
            samesite="lax",
            secure=settings.COOKIE_SECURE,
        )
        return

    @router.post("/jwt/logout", tags=["auth"])
    async def logout(response: Response) -> None:
        """Log out the current user by deleting their session cookie."""
        response.status_code = status.HTTP_204_NO_CONTENT
        response.delete_cookie(COOKIE_NAME)
        return

    @router.post("/register", status_code=202, tags=["auth"])
    async def register(
        user_create: UserCreate,
        db: AsyncSession = Depends(get_db),
        guest_user: User | None = Depends(get_optional_current_user),
    ) -> dict[str, str]:
        """Stage a pending registration and email a verification token.

        Signing up never changes the current account: the guest keeps using
        the site with full access while the email verification is pending.
        The account is promoted only after verification (deferred promotion).
        """
        if guest_user is not None and not guest_user.is_guest:
            raise HTTPException(status_code=400, detail="REGISTER_ALREADY_REAL_ACCOUNT")

        try:
            await stage_pending_registration(
                db,
                guest_user,
                user_create.email,
                user_create.password,
                user_create.username,
            )
        except sqlalchemy.exc.IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=400, detail="REGISTER_USER_ALREADY_EXISTS")

        await send_verification_email(
            user_create.email,
            (
                await db.execute(
                    select(PendingRegistration).where(
                        PendingRegistration.email == user_create.email
                    )
                )
            )
            .unique()
            .scalar_one()
            .email_verification_token,
        )
        return {"msg": "Verification email sent"}

    @router.post("/forgot-password", status_code=202, tags=["auth"])
    async def forgot_password(
        req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
    ) -> dict[str, str]:
        """Send a password reset email if the account exists."""
        stmt = select(User).where(User.email == req.email)
        user = (await db.execute(stmt)).unique().scalar_one_or_none()
        if user and user.is_active:
            token = await generate_reset_token(db, user)
            await send_forgot_password_email(user, token)
        return {"msg": "If the email is valid, a reset link was sent."}

    @router.post("/reset-password", tags=["auth"])
    async def reset_password_endpoint(
        req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
    ) -> dict[str, str]:
        """Reset a user's password using a valid token."""
        user = await reset_password(db, req.token, req.password)
        if not user:
            raise HTTPException(status_code=400, detail="RESET_PASSWORD_BAD_TOKEN")
        return {"msg": "Password reset successful"}

    @router.post("/request-verify-token", status_code=202, tags=["auth"])
    async def request_verify_token(
        req: RequestVerifyEmailRequest, db: AsyncSession = Depends(get_db)
    ) -> dict[str, str]:
        """Re-send the verification email for a staged registration."""
        stmt = select(PendingRegistration).where(PendingRegistration.email == req.email)
        pending = (await db.execute(stmt)).unique().scalar_one_or_none()
        if pending:
            await send_verification_email(
                pending.email, pending.email_verification_token
            )
        return {
            "msg": "If the email is valid and unverified, a verification link was sent."
        }

    @router.post("/verify", response_model=UserRead, tags=["auth"])
    async def verify(
        req: VerifyEmailRequest,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        """Verify the email of a pending registration.

        Promotes the linked guest account in place: same user id, so all
        guest data carries over and any live session keeps working.
        """
        try:
            user = await promote_guest_by_token(db, req.token)
        except HTTPException as exc:
            if exc.detail == "REGISTER_USER_ALREADY_EXISTS":
                raise HTTPException(status_code=400, detail="VERIFY_USER_EMAIL_TAKEN")
            raise
        if not user:
            raise HTTPException(status_code=400, detail="VERIFY_USER_BAD_TOKEN")
        return user

    @router.post("/guest", tags=["auth"])
    async def create_guest_user(
        response: Response, db: AsyncSession = Depends(get_db)
    ) -> None:
        """Create a temporary guest user account and set a session cookie."""
        guest_id = uuid.uuid4().hex[:20]
        guest_email = f"guest_{guest_id}@guest.example.com"
        guest_password = uuid.uuid4().hex

        user_create = UserCreate(
            email=guest_email,
            password=guest_password,
            is_guest=True,
        )
        user = await create_user(db, user_create)

        access_token = create_access_token(user.id)
        response.status_code = status.HTTP_204_NO_CONTENT
        response.set_cookie(
            COOKIE_NAME,
            access_token,
            max_age=3600 * 24 * 7,
            httponly=True,
            samesite="lax",
            secure=settings.COOKIE_SECURE,
        )
        return

    return router
