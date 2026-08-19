import logging
import random
import re
import string
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..config import settings
from ..models import OAuthAccount, User, UserCreate, is_reserved_username
from ..services.email import send_email
from .utils import get_password_hash

logger = logging.getLogger(__name__)


async def generate_unique_username(db: AsyncSession, email: str) -> str:
    """Generate a unique username based on the user's email."""
    base_username = email.split("@")[0]
    base_username = re.sub(r"[^a-zA-Z0-9_-]", "", base_username)
    if not base_username:
        base_username = "user"

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

    statement = select(User).where(User.username.like(f"{base_username}%"))
    results = await db.execute(statement)
    existing_users = results.unique().scalars().all()
    existing_usernames = {u.username for u in existing_users}

    if username in existing_usernames or is_reserved_username(username):
        counter = 1
        match_len = 0
        match = re.search(r"(\d+)$", username)
        if match:
            counter = int(match.group(1)) + 1
            base_username = username[: match.start()]
            match_len = len(match.group(1))

        counter_str = str(counter).zfill(match_len) if match_len > 0 else str(counter)
        truncated_base = base_username[: 32 - len(counter_str)]
        username = f"{truncated_base}{counter_str}"
        while (
            username in existing_usernames
            or is_reserved_username(username)
            or len(username) < 8
        ):
            counter += 1
            counter_str = (
                str(counter).zfill(match_len) if match_len > 0 else str(counter)
            )
            truncated_base = base_username[: 32 - len(counter_str)]
            username = f"{truncated_base}{counter_str}"

    return username


async def request_verification(db: AsyncSession, user: User) -> None:
    """Generate and send an email verification token for the user."""
    if not user.is_active or user.is_verified:
        return

    while True:
        token = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        statement = select(User).where(User.email_verification_token == token)
        results = await db.execute(statement)
        existing_user = results.unique().scalars().first()
        if not existing_user:
            break

    user.email_verification_token = token
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("Verification requested for user %s", user.id)
    verify_url = f"{settings.FRONTEND_URL}/verify?token={token}"
    subject = "Verify your Cardie email address"
    content = f"Please verify your email address by clicking the following link:\n\n{verify_url}\n\nOr use this code: {token}"
    await send_email(user.email, subject, content)


async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
    """Create a new user and trigger email verification if necessary."""
    username = user_create.username
    if username:
        if is_reserved_username(username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="USERNAME_RESERVED",
            )
    else:
        username = await generate_unique_username(db, user_create.email)

    display_name = user_create.display_name
    if not display_name:
        display_name = username

    hashed_password = get_password_hash(user_create.password)

    db_user = User(
        email=user_create.email,
        hashed_password=hashed_password,
        username=username,
        display_name=display_name,
        is_guest=user_create.is_guest,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    if not db_user.is_guest and not db_user.is_verified:
        await request_verification(db, db_user)

    return db_user


async def _apply_guest_upgrade(
    db: AsyncSession,
    guest_user: User,
    email: str,
    password: str,
    username: str | None,
    is_verified: bool,
) -> User:
    """Set account fields on a guest user without committing."""
    if username:
        if is_reserved_username(username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="USERNAME_RESERVED",
            )
    else:
        username = await generate_unique_username(db, email)

    guest_user.email = email
    guest_user.hashed_password = get_password_hash(password)
    guest_user.username = username
    guest_user.display_name = username
    guest_user.is_guest = False
    guest_user.is_verified = is_verified
    guest_user.email_verification_token = None
    guest_user.reset_password_token = None

    db.add(guest_user)
    return guest_user


async def upgrade_guest_user(
    db: AsyncSession,
    guest_user: User,
    email: str,
    password: str,
    username: str | None = None,
) -> User:
    """Convert a guest account into a regular account in place.

    The guest's user_id is preserved so all owned data (decks, folders,
    learning progress, stars, activity) stays attached to the account.
    """
    await _apply_guest_upgrade(db, guest_user, email, password, username, False)
    await db.commit()
    await db.refresh(guest_user)

    if not guest_user.is_verified:
        await request_verification(db, guest_user)

    return guest_user


async def handle_oauth_callback(
    db: AsyncSession,
    oauth_name: str,
    access_token: str,
    account_id: str,
    account_email: str,
    expires_at: int | None = None,
    refresh_token: str | None = None,
    guest_user: User | None = None,
) -> User:
    """Process OAuth callback, linking or creating the user account.

    A guest session is the account being signed up/in: a new Google identity
    upgrades the guest in place; an existing Google identity (or existing
    email) signs the guest into that account and discards the guest account.
    Guest data is never merged.
    """
    is_guest_session = guest_user is not None and guest_user.is_guest

    # First, try to find user by oauth account
    stmt = select(OAuthAccount).where(
        OAuthAccount.oauth_name == oauth_name, OAuthAccount.account_id == account_id
    )
    res = await db.execute(stmt)
    oauth_acc = res.scalar_one_or_none()

    if oauth_acc:
        # Update tokens
        oauth_acc.access_token = access_token
        oauth_acc.expires_at = expires_at
        oauth_acc.refresh_token = refresh_token
        db.add(oauth_acc)

        user_stmt = select(User).where(User.id == oauth_acc.user_id)
        user = (await db.execute(user_stmt)).unique().scalar_one_or_none()
        if user:
            user.last_active_at = datetime.now(timezone.utc)
            db.add(user)
        # Only discard the guest when signing into a distinct, existing account.
        if is_guest_session and user is not None and oauth_acc.user_id != guest_user.id:
            await db.delete(guest_user)
        await db.commit()
        return user

    # Associate by email or create new user
    user_stmt = select(User).where(User.email == account_email)
    user = (await db.execute(user_stmt)).unique().scalar_one_or_none()

    if not user:
        if is_guest_session:
            # Google sign-up from a guest session upgrades the guest in place
            # (single transaction with the OAuthAccount link below).
            random_password = "".join(
                random.choices(string.ascii_letters + string.digits, k=32)
            )
            user = await _apply_guest_upgrade(
                db, guest_user, account_email, random_password, None, True
            )
        else:
            # Create new user
            # Note: OAuth users do not have a standard password, we use a random string
            # Since we use passlib, we can just hash a random password
            random_password = "".join(
                random.choices(string.ascii_letters + string.digits, k=32)
            )
            hashed_password = get_password_hash(random_password)
            username = await generate_unique_username(db, account_email)

            user = User(
                email=account_email,
                hashed_password=hashed_password,
                username=username,
                display_name=username,
                is_verified=True,  # Trust Google
            )
            db.add(user)
        await db.flush()  # To get user.id for OAuthAccount
    elif is_guest_session:
        # Existing account: this is a sign-in, discard the guest session.
        await db.delete(guest_user)

    # Add OAuth account
    new_oauth = OAuthAccount(
        oauth_name=oauth_name,
        access_token=access_token,
        account_id=account_id,
        account_email=account_email,
        expires_at=expires_at,
        refresh_token=refresh_token,
        user_id=user.id,
    )
    db.add(new_oauth)
    await db.commit()
    await db.refresh(user)

    # Note: we skip verification request since Google provides a verified email
    return user


async def generate_reset_token(db: AsyncSession, user: User) -> str:
    """Generate a unique password reset token for the user."""
    while True:
        token = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        statement = select(User).where(User.reset_password_token == token)
        results = await db.execute(statement)
        if not results.unique().scalars().first():
            break

    user.reset_password_token = token
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return token


async def send_forgot_password_email(user: User, token: str) -> None:
    logger.info("Password reset requested for user %s", user.id)
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = "Reset your Cardie password"
    content = f"You requested a password reset. Click the following link to reset your password:\n\n{reset_url}\n\nOr use this code: {token}"
    await send_email(user.email, subject, content)


async def reset_password(
    db: AsyncSession, token: str, new_password: str
) -> User | None:
    """Reset the user's password using the provided token."""
    statement = select(User).where(User.reset_password_token == token)
    result = await db.execute(statement)
    user = result.unique().scalar_one_or_none()
    if not user:
        return None

    user.hashed_password = get_password_hash(new_password)
    user.reset_password_token = None
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
