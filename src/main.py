from contextlib import asynccontextmanager

from fastapi import FastAPI

from .auth.router import create_auth_router
from .database import create_db_and_tables
from .routers import cards, decks


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

# --- Auth routes ---
app.include_router(create_auth_router(), prefix="/auth", tags=["auth"])

# --- App routes ---
app.include_router(decks.router)
app.include_router(cards.router)
