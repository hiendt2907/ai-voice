from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import Settings
from .routers import calls, health, preview, ws

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="AI Voice Worker", version="0.0.1", lifespan=lifespan)
app.include_router(health.router)
app.include_router(preview.router)
app.include_router(calls.router)
app.include_router(ws.router)
