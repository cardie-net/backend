from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)

from ..config import settings

LIFETIME_SECONDS = 3600 * 24 * 7  # 7 days

cookie_transport = CookieTransport(
    cookie_name="cardie_session",
    cookie_max_age=LIFETIME_SECONDS,
    cookie_secure=settings.FRONTEND_URL.startswith("https"),
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.SECRET_KEY, lifetime_seconds=LIFETIME_SECONDS)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
