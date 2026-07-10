from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.router import create_auth_router
from .database import create_db_and_tables
from .routers import cards, decks, folders, users


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth routes ---
app.include_router(create_auth_router(), prefix="/v1/auth", tags=["auth"])

# --- App routes ---
app.include_router(folders.router, prefix="/v1")
app.include_router(decks.router, prefix="/v1")
app.include_router(cards.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
