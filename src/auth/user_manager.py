import random
import re
import string
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions, models, schemas
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

    async def _generate_unique_username(self, email: str) -> str:
        base_username = email.split("@")[0]
        # url-safe characters only
        base_username = re.sub(r"[^a-zA-Z0-9_-]", "", base_username)
        if not base_username:
            base_username = "user"

        # truncate to ensure it fits in 32 chars along with any numbers appended
        base_username = base_username[:26]

        username = base_username
        if len(username) < 8:
            padding_length = 8 - len(username)
            first_digit = random.choice(string.digits[1:])
            other_digits = (
                "".join(random.choices(string.digits, k=padding_length - 1))
                if padding_length > 1
                else ""
            )
            username += first_digit + other_digits

        statement = select(self.user_db.user_model).where(
            self.user_db.user_model.username.like(f"{base_username}%")
        )
        results = await self.user_db.session.execute(statement)
        existing_users = results.unique().all()
        existing_usernames = {u[0].username for u in existing_users}

        if username in existing_usernames:
            counter = 1
            match_len = 0
            match = re.search(r"(\d+)$", username)
            if match:
                counter = int(match.group(1)) + 1
                base_username = username[: match.start()]
                match_len = len(match.group(1))

            counter_str = (
                str(counter).zfill(match_len) if match_len > 0 else str(counter)
            )
            username = f"{base_username}{counter_str}"
            while username in existing_usernames:
                counter += 1
                counter_str = (
                    str(counter).zfill(match_len) if match_len > 0 else str(counter)
                )
                username = f"{base_username}{counter_str}"

        return username

    async def create(
        self,
        user_create: schemas.UC,
        safe: bool = False,
        request: Optional[Request] = None,
    ) -> models.UP:
        if getattr(user_create, "username", None) is None:
            username = await self._generate_unique_username(user_create.email)
            user_create.username = username
        if getattr(user_create, "display_name", None) is None:
            user_create.display_name = user_create.username

        return await super().create(user_create, safe=safe, request=request)

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        request: Optional[Request] = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> User:
        oauth_account_dict = {
            "oauth_name": oauth_name,
            "access_token": access_token,
            "account_id": account_id,
            "account_email": account_email,
            "expires_at": expires_at,
            "refresh_token": refresh_token,
        }

        try:
            user = await self.get_by_oauth_account(oauth_name, account_id)
        except exceptions.UserNotExists:
            try:
                # Associate account
                user = await self.get_by_email(account_email)
                if not associate_by_email:
                    raise exceptions.UserAlreadyExists()
                user = await self.user_db.add_oauth_account(user, oauth_account_dict)
            except exceptions.UserNotExists:
                # Create account
                password = self.password_helper.generate()
                username = await self._generate_unique_username(account_email)
                user_dict = {
                    "email": account_email,
                    "hashed_password": self.password_helper.hash(password),
                    "is_verified": is_verified_by_default,
                    "username": username,
                    "display_name": username,
                }
                user = await self.user_db.create(user_dict)
                user = await self.user_db.add_oauth_account(user, oauth_account_dict)
                await self.on_after_register(user, request)
        else:
            # Update oauth
            for existing_oauth_account in user.oauth_accounts:
                if (
                    existing_oauth_account.account_id == account_id
                    and existing_oauth_account.oauth_name == oauth_name
                ):
                    user = await self.user_db.update_oauth_account(
                        user, existing_oauth_account, oauth_account_dict
                    )

        return user

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        print(f"User {user.id} has registered.")
        if not user.is_guest and not user.is_verified:
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
