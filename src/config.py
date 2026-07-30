from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///./sql_app.db"
    JWT_ALGORITHM: str = "HS256"

    # Image Settings
    IMAGE_MAX_SIZE: int = 512
    IMAGE_QUALITY: int = 80

    # Email Settings
    SMTP_SERVER: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = "noreply@example.com"
    EMAIL_DOMAIN: str = "cardie.net"
    SMTP_TIMEOUT: int = 5
    FRONTEND_URL: str = "http://localhost:3000"

    # AWS S3 Settings
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = ""
    AWS_ENDPOINT_URL: str = ""
    S3_PUBLIC_URL: str = ""
    S3_AVATAR_PREFIX: str = "avatars/"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
