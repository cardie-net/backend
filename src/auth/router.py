import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..database import get_db
from ..models import User, UserCreate, UserRead
from .google_oauth_router import create_google_oauth_router
from .service import (
    create_user,
    generate_reset_token,
    request_verification,
    reset_password,
    send_forgot_password_email,
)
from .utils import (
    COOKIE_NAME,
    create_access_token,
    current_active_user,
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
    ):
        stmt = select(User).where(User.email == credentials.username)
        user = (await db.execute(stmt)).unique().scalar_one_or_none()

        if not user or user.is_guest:
            raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")
        if not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")
        if not user.is_verified:
            raise HTTPException(status_code=400, detail="USER_NOT_VERIFIED")

        access_token = create_access_token(user.id)
        # We return 204 typically or we can return 200 with JSON if swagger needs it, but the tests check for 204 for login success or 200 depending. Wait, the old login returned 204 and set a cookie. Actually, fastapi-users returns JSON with access_token. But wait, in test_auth.py test_login_verified_user it checks `assert response.status_code == 204` and `assert "cardie_session" in response.cookies`. So it returned 204.
        response.status_code = status.HTTP_204_NO_CONTENT
        response.set_cookie(
            COOKIE_NAME,
            access_token,
            max_age=3600 * 24 * 7,
            httponly=True,
            samesite="lax",
            secure=False,  # Should be set via settings, hardcoding for now
        )
        return

    @router.post("/jwt/logout", tags=["auth"])
    async def logout(response: Response):
        response.status_code = status.HTTP_204_NO_CONTENT
        response.delete_cookie(COOKIE_NAME)
        return

    @router.post("/register", response_model=UserRead, status_code=201, tags=["auth"])
    async def register(user_create: UserCreate, db: AsyncSession = Depends(get_db)):
        stmt = select(User).where(User.email == user_create.email)
        existing = (await db.execute(stmt)).unique().scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="REGISTER_USER_ALREADY_EXISTS")

        return await create_user(db, user_create)

    @router.post("/forgot-password", status_code=202, tags=["auth"])
    async def forgot_password(
        req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
    ):
        stmt = select(User).where(User.email == req.email)
        user = (await db.execute(stmt)).unique().scalar_one_or_none()
        if user and user.is_active:
            token = await generate_reset_token(db, user)
            await send_forgot_password_email(user, token)
        return {"msg": "If the email is valid, a reset link was sent."}

    @router.post("/reset-password", tags=["auth"])
    async def reset_password_endpoint(
        req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
    ):
        user = await reset_password(db, req.token, req.password)
        if not user:
            raise HTTPException(status_code=400, detail="RESET_PASSWORD_BAD_TOKEN")
        return {"msg": "Password reset successful"}

    @router.post("/request-verify-token", status_code=202, tags=["auth"])
    async def request_verify_token(
        req: RequestVerifyEmailRequest, db: AsyncSession = Depends(get_db)
    ):
        stmt = select(User).where(User.email == req.email)
        user = (await db.execute(stmt)).unique().scalar_one_or_none()
        if user and not user.is_verified and user.is_active:
            await request_verification(db, user)
        return {
            "msg": "If the email is valid and unverified, a verification link was sent."
        }

    @router.post("/verify", response_model=UserRead, tags=["auth"])
    async def verify(req: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
        stmt = select(User).where(User.email_verification_token == req.token)
        user = (await db.execute(stmt)).unique().scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=400, detail="VERIFY_USER_BAD_TOKEN")
        if user.is_verified:
            raise HTTPException(status_code=400, detail="VERIFY_USER_ALREADY_VERIFIED")

        user.is_verified = True
        user.email_verification_token = None
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @router.post("/guest", tags=["auth"])
    async def create_guest_user(response: Response, db: AsyncSession = Depends(get_db)):
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
            secure=False,
        )
        return

    return router
