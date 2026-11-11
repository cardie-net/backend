from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth.router import create_auth_router
from .config import settings
from .database import create_db_and_tables
from .middleware import UploadSizeLimitMiddleware, upload_too_large_response
from .routers import cards, community, decks, folders, srs, users
from .services.image_service import ImageTooLargeError, UnsupportedImageError
from .utils import FileTooLargeError


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(
    title="Cardie API",
    description="API documentation for the Cardie application.",
    version="1.0.0",
    lifespan=lifespan,
)


# Added before CORS so CORS stays outermost and decorates early 413 responses.
app.add_middleware(UploadSizeLimitMiddleware)

# Credentials are allowed, so the origin list must be explicit: Starlette
# reflects any Origin when the list is "*", which would let other sites read
# authenticated responses. settings.cors_origins never contains a wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FileTooLargeError)
async def file_too_large_exception_handler(request: Request, exc: FileTooLargeError):
    return upload_too_large_response()


@app.exception_handler(UnsupportedImageError)
async def unsupported_image_handler(
    request: Request, exc: UnsupportedImageError
) -> JSONResponse:
    """Reject uploads that are not decodable images in an allowed format."""
    return JSONResponse(status_code=415, content={"detail": "Unsupported image file"})


@app.exception_handler(ImageTooLargeError)
async def image_too_large_handler(
    request: Request, exc: ImageTooLargeError
) -> JSONResponse:
    """Reject images whose decoded pixel count exceeds MAX_IMAGE_PIXELS."""
    return JSONResponse(
        status_code=413,
        content={
            "detail": "Image dimensions too large",
            "max_pixels": settings.MAX_IMAGE_PIXELS,
        },
    )


# --- Auth routes ---
app.include_router(create_auth_router(), prefix="/api/v1/auth", tags=["auth"])

# --- App routes ---
app.include_router(folders.router, prefix="/api/v1")
app.include_router(decks.router, prefix="/api/v1")
app.include_router(cards.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(srs.router, prefix="/api/v1")
app.include_router(community.router, prefix="/api/v1")
