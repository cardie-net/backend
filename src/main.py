from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.router import create_auth_router
from .database import create_db_and_tables
from .routers import cards, decks


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(
    title="cardie.net API",
    description="API documentation for cardie.net.",
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
app.include_router(create_auth_router(), prefix="/auth", tags=["auth"])

# --- App routes ---
app.include_router(decks.router)
app.include_router(cards.router)
