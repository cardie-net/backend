import random
import string
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from fastapi_users_db_sqlmodel import SQLModelUserDatabaseAsync
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..config import settings
from ..database import get_db
from ..models import OAuthAccount, User
from ..services.email import send_email


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        print(f"User {user.id} has registered.")
        if not user.is_guest:
            await self.request_verify(user, request)

    async def on_after_login(
        self,
        user: User,
        request: Optional[Request] = None,
        response=None,
    ) -> None:
        print(f"User {user.id} has logged in.")

    async def authenticate(
        self, credentials: OAuth2PasswordRequestForm
    ) -> Optional[User]:
        user = await super().authenticate(credentials)
        if user is None:
            return None
        if user.is_guest:
            return None
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="USER_NOT_VERIFIED",
            )
        return user

    async def request_verify(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        if not user.is_active:
            raise exceptions.UserInactive()
        if user.is_verified:
            raise exceptions.UserAlreadyVerified()

        # Generate a unique short 10-character alphanumeric code
        while True:
            token = "".join(random.choices(string.ascii_letters + string.digits, k=10))
            statement = select(self.user_db.user_model).where(
                self.user_db.user_model.email_verification_token == token
            )
            results = await self.user_db.session.execute(statement)
            existing_user = results.first()
            if not existing_user:
                break

        # Save it to the user object
        user = await self.user_db.update(user, {"email_verification_token": token})

        await self.on_after_request_verify(user, token, request)

    async def verify(self, token: str, request: Optional[Request] = None) -> User:
        # Find user by token
        statement = select(self.user_db.user_model).where(
            self.user_db.user_model.email_verification_token == token
        )
        results = await self.user_db.session.execute(statement)
        user = results.first()

        if not user:
            raise exceptions.InvalidVerifyToken()

        user = user[0]

        if user.is_verified:
            raise exceptions.UserAlreadyVerified()

        # Mark as verified and clear the token
        verified_user = await self.user_db.update(
            user, {"is_verified": True, "email_verification_token": None}
        )

        await self.on_after_verify(verified_user, request)

        return verified_user

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        print(f"Verification requested for user {user.id}.")
        verify_url = f"{settings.FRONTEND_URL}/verify?token={token}"

        subject = "Verify your Cardie email address"
        content = f"Please verify your email address by clicking the following link:\n\n{verify_url}\n\nOr use this code: {token}"
        await send_email(user.email, subject, content)

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        print(f"User {user.id} forgot their password.")
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

        subject = "Reset your Cardie password"
        content = f"You requested a password reset. Click the following link to reset your password:\n\n{reset_url}\n\nOr use this code: {token}"
        await send_email(user.email, subject, content)


async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield SQLModelUserDatabaseAsync(session, User, OAuthAccount)


async def get_user_manager(
    user_db: SQLModelUserDatabaseAsync = Depends(get_user_db),
):
    yield UserManager(user_db)
