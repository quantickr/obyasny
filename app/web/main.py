from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.logging import setup_logging
from app.web.dependencies import RequireLoginRedirect
from app.web.routers import (
    auth,
    chat,
    listings,
    matches,
    profile,
    requests,
    search,
    topics,
)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(title="Объясни!", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)


@app.exception_handler(RequireLoginRedirect)
async def require_login_handler(request: Request, exc: RequireLoginRedirect):
    return RedirectResponse(url="/login", status_code=303)


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(search.router)
app.include_router(requests.router)
app.include_router(chat.router)
app.include_router(listings.router)
app.include_router(matches.router)
app.include_router(topics.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
