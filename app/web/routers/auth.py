import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import settings
from app.core.profanity import ProfanityError
from app.core.security import create_session_token, verify_telegram_login
from app.models.user import EduLevel
from app.services import (
    email_service,
    email_verify_service,
    password_reset_service,
    user_service,
)
from app.services.email_verify_service import TooSoonError
from app.services.password_reset_service import TooSoonError as ResetTooSoonError
from app.services.user_service import AuthError
from app.web.dependencies import (
    SESSION_COOKIE,
    CurrentUserOptional,
    CurrentUserUnverified,
    SessionDep,
)
from app.web.templating import templates


def _mask_email(email: str) -> str:
    """Маскирует email для отображения: joh***@example.com."""
    local, _, domain = email.partition("@")
    if not domain:
        return email
    visible = local[:3]
    return f"{visible}{'*' * max(len(local) - 3, 1)}@{domain}"


async def _send_code_safe(user_id: int, email: str) -> str:
    """Генерирует код и шлёт письмо. Возвращает notice для query.

    Не бросает исключений — всегда возвращает строку-подсказку.
    """
    try:
        code = await email_verify_service.issue_code(user_id, email)
    except TooSoonError:
        return "toosoon"
    try:
        await email_service.send_verification_code(email, code)
    except email_service.EmailError:
        return "mailfail"
    return "sent"


async def _send_reset_safe(email: str) -> str:
    """Генерирует код сброса пароля и шлёт письмо. Возвращает notice.

    Не бросает исключений — всегда возвращает строку-подсказку.
    """
    try:
        code = await password_reset_service.issue_code(email)
    except ResetTooSoonError:
        return "toosoon"
    try:
        await email_service.send_password_reset_code(email, code)
    except email_service.EmailError:
        return "mailfail"
    return "sent"

router = APIRouter()

_COOKIE_MAX_AGE = settings.session_ttl_hours * 3600


def _set_session(response: RedirectResponse, user_id: int) -> None:
    token = create_session_token(user_id)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: CurrentUserOptional):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "bot_username": settings.bot_username},
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, reset: str = ""):
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {"user": None, "error": None, "reset": reset},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
):
    try:
        user = await user_service.authenticate_email(session, email, password)
    except AuthError as e:
        return templates.TemplateResponse(
            request, "auth/login.html", {"user": None, "error": str(e)}
        )
    response = RedirectResponse(url="/profile", status_code=303)
    _set_session(response, user.id)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request, "auth/register.html", {"user": None, "error": None}
    )


@router.post("/register")
async def register_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    display_name: str = Form(...),
    university: str = Form(...),
    course: str = Form(...),
    edu_level: str = Form(...),
):
    def _reject(msg: str):
        return templates.TemplateResponse(
            request, "auth/register.html", {"user": None, "error": msg}
        )

    if password != password_confirm:
        return _reject("Пароли не совпадают")
    if not course.isdigit() or not (1 <= int(course) <= 11):
        return _reject("Курс/класс должен быть числом от 1 до 11")
    try:
        level = EduLevel(edu_level)
    except ValueError:
        return _reject("Некорректный уровень обучения")
    # Школьник учится в школе — вуз не требуем, подставляем сами.
    if level == EduLevel.schoolchild:
        university = "Школа"
    elif not university.strip():
        return _reject("Укажите вуз")

    try:
        user = await user_service.register_email(
            session,
            email,
            password,
            display_name,
            university=university,
            course=int(course),
            edu_level=level,
        )
        await session.commit()
    except ProfanityError as e:
        return _reject(str(e))
    except AuthError as e:
        return _reject(str(e))
    # Отправляем код подтверждения и ведём на страницу ввода кода.
    notice = await _send_code_safe(user.id, user.email)
    response = RedirectResponse(
        url=f"/verify-email?notice={notice}", status_code=303
    )
    _set_session(response, user.id)
    return response


@router.get("/auth/telegram")
async def telegram_callback(request: Request, session: SessionDep):
    """Callback от Telegram Login Widget: проверяем подпись и логиним."""
    data = dict(request.query_params)
    if not verify_telegram_login(data):
        return RedirectResponse(url="/login?error=tg", status_code=303)

    # Защита от старых данных (auth_date не старше суток)
    auth_date = int(data.get("auth_date", "0"))
    if time.time() - auth_date > 86400:
        return RedirectResponse(url="/login?error=expired", status_code=303)

    tg_id = int(data["id"])
    username = data.get("username")
    display_name = data.get("first_name") or username or "Студент"
    user = await user_service.get_or_create_telegram_user(
        session, tg_id, username, display_name
    )
    await session.commit()

    response = RedirectResponse(url="/profile", status_code=303)
    _set_session(response, user.id)
    return response


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page(
    request: Request,
    user: CurrentUserUnverified,
    error: str = "",
    notice: str = "",
):
    # Нет email или уже подтверждён — здесь делать нечего.
    if user.email is None or user.email_verified:
        return RedirectResponse(url="/profile", status_code=303)
    return templates.TemplateResponse(
        request,
        "auth/verify_email.html",
        {
            "user": None,  # шапку не показываем как для залогиненного
            "email_masked": _mask_email(user.email),
            "error": error,
            "notice": notice,
        },
    )


@router.post("/verify-email")
async def verify_email_submit(
    request: Request,
    session: SessionDep,
    user: CurrentUserUnverified,
    code: str = Form(...),
):
    if user.email is None or user.email_verified:
        return RedirectResponse(url="/profile", status_code=303)
    verified_email = await email_verify_service.verify_code(user.id, code)
    if verified_email is None or verified_email != user.email:
        return RedirectResponse(
            url="/verify-email?error=badcode", status_code=303
        )
    await user_service.set_email_verified(session, user)
    await session.commit()
    return RedirectResponse(url="/profile?saved=1", status_code=303)


@router.post("/verify-email/resend")
async def verify_email_resend(user: CurrentUserUnverified):
    if user.email is None or user.email_verified:
        return RedirectResponse(url="/profile", status_code=303)
    notice = await _send_code_safe(user.id, user.email)
    return RedirectResponse(
        url=f"/verify-email?notice={notice}", status_code=303
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request, error: str = "", notice: str = ""
):
    return templates.TemplateResponse(
        request,
        "auth/forgot_password.html",
        {"user": None, "error": error, "notice": notice},
    )


@router.post("/forgot-password")
async def forgot_password_submit(
    session: SessionDep,
    email: str = Form(...),
):
    email = email.lower().strip()
    user = await user_service.get_by_email(session, email)
    # Шлём код только реальному аккаунту с паролем. В любом случае ведём на
    # страницу ввода кода с нейтральным текстом (anti-enumeration).
    if user and user.password_hash:
        notice = await _send_reset_safe(email)
    else:
        notice = "sent"
    return RedirectResponse(
        url=f"/reset-password?email={email}&notice={notice}",
        status_code=303,
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request, email: str = "", error: str = "", notice: str = ""
):
    if not email.strip():
        return RedirectResponse(url="/forgot-password", status_code=303)
    return templates.TemplateResponse(
        request,
        "auth/reset_password.html",
        {"user": None, "email": email, "error": error, "notice": notice},
    )


@router.post("/reset-password")
async def reset_password_submit(
    session: SessionDep,
    email: str = Form(...),
    code: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    email = email.lower().strip()

    def _reject(err: str):
        return RedirectResponse(
            url=f"/reset-password?email={email}&error={err}", status_code=303
        )

    if password != password_confirm:
        return _reject("nomatch")
    if len(password) < 6:
        return _reject("short")
    if not await password_reset_service.verify_code(email, code):
        return _reject("badcode")
    user = await user_service.get_by_email(session, email)
    if user is None or not user.password_hash:
        return _reject("badcode")
    await user_service.reset_password(session, user, password)
    await session.commit()
    return RedirectResponse(url="/login?reset=1", status_code=303)


@router.post("/reset-password/resend")
async def reset_password_resend(email: str = Form(...)):
    email = email.lower().strip()
    notice = await _send_reset_safe(email)
    return RedirectResponse(
        url=f"/reset-password?email={email}&notice={notice}", status_code=303
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
