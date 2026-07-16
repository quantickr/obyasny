import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import settings
from app.core.profanity import ProfanityError
from app.core.security import create_session_token, verify_telegram_login
from app.models.user import EduLevel
from app.services import user_service
from app.services.user_service import AuthError
from app.web.dependencies import SESSION_COOKIE, CurrentUserOptional, SessionDep
from app.web.templating import templates

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
    if user:
        return RedirectResponse(url="/profile", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"user": None})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request, "auth/login.html", {"user": None, "error": None}
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
    display_name: str = Form(...),
    university: str = Form(...),
    course: str = Form(...),
    edu_level: str = Form(...),
):
    def _reject(msg: str):
        return templates.TemplateResponse(
            request, "auth/register.html", {"user": None, "error": msg}
        )

    if not course.isdigit() or not (1 <= int(course) <= 6):
        return _reject("Курс должен быть числом от 1 до 6")
    try:
        level = EduLevel(edu_level)
    except ValueError:
        return _reject("Некорректный уровень обучения")
    if not university.strip():
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
    response = RedirectResponse(url="/profile", status_code=303)
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


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
