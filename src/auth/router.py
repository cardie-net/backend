import uuid

from fastapi import APIRouter, Depends
from fastapi_users import FastAPIUsers

from ..models import User, UserCreate, UserRead
from .backend import auth_backend, get_jwt_strategy
from .google_oauth_router import create_google_oauth_router
from .user_manager import UserManager, get_user_manager

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# Dependency to get the current active user
current_active_user = fastapi_users.current_user(active=True)


def create_auth_router() -> APIRouter:
    """Assemble and return the full auth router."""
    router = APIRouter()

    # JWT login / logout
    router.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/jwt",
        tags=["auth"],
    )

    # Registration
    router.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        tags=["auth"],
    )

    # Password reset
    router.include_router(
        fastapi_users.get_reset_password_router(),
        tags=["auth"],
    )

    # Email verification
    router.include_router(
        fastapi_users.get_verify_router(UserRead),
        tags=["auth"],
    )

    # Google OAuth (custom router with frontend redirect)
    router.include_router(
        create_google_oauth_router(),
        prefix="/google",
        tags=["auth"],
    )

    # Guest endpoint
    @router.post("/guest", tags=["auth"])
    async def create_guest_user(
        user_manager: UserManager = Depends(get_user_manager),
    ):
        """Create a guest user and return a JWT token."""
        # Generate a unique placeholder email for the guest
        guest_id = uuid.uuid4().hex[:20]
        guest_email = f"guest_{guest_id}@guest.example.com"
        guest_password = uuid.uuid4().hex

        user_create = UserCreate(
            email=guest_email,
            password=guest_password,
            is_guest=True,
        )
        user = await user_manager.create(user_create, safe=False)

        # Generate a JWT token for the guest
        strategy = get_jwt_strategy()
        token = await strategy.write_token(user)

        return {"access_token": token, "token_type": "bearer"}

    return router
