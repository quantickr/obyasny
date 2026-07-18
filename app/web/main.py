from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import setup_logging
from app.services import user_service
from app.web.csrf import CSRFMiddleware
from app.web.dependencies import (
    RequireAdminAccess,
    RequireBanned,
    RequireEmailVerification,
    RequireLoginRedirect,
)
from app.web.routers import (
    admin,
    auth,
    chat,
    listings,
    matches,
    profile,
    reports,
    requests,
    search,
    topics,
    universities,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path("/app/uploads")


async def _ensure_admin() -> None:
    """Назначает суперадмина пользователю с email из настроек (если задан).

    Суперадмин получает полный набор прав и возможность назначать мини-админов.
    """
    email = settings.admin_email.strip().lower()
    if not email:
        return
    async with async_session_factory() as session:
        user = await user_service.get_by_email(session, email)
        if user is None:
            return
        changed = False
        for attr in (
            "is_admin",
            "is_superadmin",
            "can_manage_reports",
            "can_punish",
            "can_edit_profiles",
        ):
            if not getattr(user, attr):
                setattr(user, attr, True)
                changed = True
        if changed:
            await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    (UPLOAD_DIR / "avatars").mkdir(parents=True, exist_ok=True)
    await _ensure_admin()
    yield


app = FastAPI(
    title="Объясни!",
    lifespan=lifespan,
    # В проде скрываем Swagger/ReDoc/OpenAPI: они раскрывают всю карту API.
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    openapi_url=None if settings.is_prod else "/openapi.json",
)

# CSRF-защита форм (double-submit cookie). Регистрируем как middleware-класс,
# чтобы он оборачивал HTML-ответы и добавлял скрытое поле в формы.
app.add_middleware(CSRFMiddleware)


@app.middleware("http")
async def _no_store_dynamic(request: Request, call_next):
    """Запрещает кэширование динамических ответов (HTML, редиректы с Set-Cookie,
    JSON). Без этого прокси/CDN может закэшировать персональную страницу или
    ответ с cookie сессии и отдать её другому пользователю. Статику и загрузки
    (их отдаёт nginx с expires) кэшировать можно."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") or path.startswith("/uploads/"):
        return response
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, private"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


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


@app.exception_handler(RequireBanned)
async def require_banned_handler(request: Request, exc: RequireBanned):
    return RedirectResponse(url="/banned", status_code=303)


@app.exception_handler(RequireAdminAccess)
async def require_admin_handler(request: Request, exc: RequireAdminAccess):
    return RedirectResponse(url="/", status_code=303)


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(search.router)
app.include_router(requests.router)
app.include_router(chat.router)
app.include_router(listings.router)
app.include_router(matches.router)
app.include_router(topics.router)
app.include_router(universities.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.get("/banned", response_class=PlainTextResponse)
async def banned_page():
    """Страница-заглушка для забаненных пользователей."""
    return (
        "Ваш аккаунт заблокирован администратором за нарушение правил.\n"
        "Если это ошибка — напишите в поддержку."
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get(
    "/mailru-verification5ca00a8e5eb37295.html",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
async def mailru_domain_verification():
    """Подтверждение владения доменом obyasny.ru для postmaster.mail.ru."""
    return "mailru-verification: 5ca00a8e5eb37295"
