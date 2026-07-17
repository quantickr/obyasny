from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.logging import setup_logging
from app.web.dependencies import RequireEmailVerification, RequireLoginRedirect
from app.web.routers import (
    auth,
    chat,
    listings,
    matches,
    profile,
    requests,
    search,
    topics,
    universities,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path("/app/uploads")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    (UPLOAD_DIR / "avatars").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Объясни!", lifespan=lifespan)

# Директория загрузок должна существовать до монтирования StaticFiles.
(UPLOAD_DIR / "avatars").mkdir(parents=True, exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

# Fallback для dev: в проде отдаёт nginx (location /uploads/).
app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploads",
)


@app.exception_handler(RequireLoginRedirect)
async def require_login_handler(request: Request, exc: RequireLoginRedirect):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(RequireEmailVerification)
async def require_email_verification_handler(
    request: Request, exc: RequireEmailVerification
):
    return RedirectResponse(url="/verify-email", status_code=303)


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(search.router)
app.include_router(requests.router)
app.include_router(chat.router)
app.include_router(listings.router)
app.include_router(matches.router)
app.include_router(topics.router)
app.include_router(universities.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
