from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///./sql_app.db"
    JWT_ALGORITHM: str = "HS256"

    # Image Settings (dimensions in pixels; MAX_UPLOAD_SIZE in bytes)
    AVATAR_MAX_SIZE: int = 512
    IMAGE_QUALITY: int = 80
    CARD_IMAGE_MAX_SIZE: int = 1024
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB
    # Upper bound on decoded pixels per upload. A tiny compressed file can
    # otherwise expand into hundreds of MiB of decoder memory.
    MAX_IMAGE_PIXELS: int = 40_000_000
    # Upload abuse limits: total stored image bytes per user and uploads/minute.
    MAX_USER_STORAGE_BYTES: int = 100 * 1024 * 1024  # 100 MB
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = 20

    # Email Settings
    SMTP_SERVER: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = "noreply@example.com"
    EMAIL_DOMAIN: str = "cardie.net"
    SMTP_TIMEOUT: int = 5
    FRONTEND_URL: str = "http://localhost:3000"

    # Public base URL of this API, e.g. "https://cardie.net". Set it when the
    # backend runs behind a TLS-terminating reverse proxy: it is used to build
    # absolute URLs (Google OAuth redirect_uri) with the correct external
    # scheme/host instead of whatever the backend sees internally.
    PUBLIC_BACKEND_URL: str = ""
    # Set True in production (HTTPS) so session cookies carry the Secure flag.
    COOKIE_SECURE: bool = False

    # AWS S3 Settings
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = ""
    AWS_ENDPOINT_URL: str = ""
    S3_PUBLIC_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
