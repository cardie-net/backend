from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .auth.router import create_auth_router
from .database import create_db_and_tables
from .middleware import UploadSizeLimitMiddleware, upload_too_large_response
from .routers import cards, community, decks, folders, srs, users
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FileTooLargeError)
async def file_too_large_exception_handler(request: Request, exc: FileTooLargeError):
    return upload_too_large_response()


# --- Auth routes ---
app.include_router(create_auth_router(), prefix="/api/v1/auth", tags=["auth"])

# --- App routes ---
app.include_router(folders.router, prefix="/api/v1")
app.include_router(decks.router, prefix="/api/v1")
app.include_router(cards.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(srs.router, prefix="/api/v1")
app.include_router(community.router, prefix="/api/v1")
