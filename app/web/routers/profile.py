from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.profanity import ProfanityError
from app.models.topic import TopicKind
from app.models.user import EduLevel
from app.services import (
    chocolate_service,
    email_service,
    email_verify_service,
    linking_service,
    topic_service,
    upload_service,
    user_service,
)
from app.services.email_verify_service import TooSoonError
from app.services.user_service import AuthError
from app.web.dependencies import CurrentUser, CurrentUserOptional, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    error: str = "",
    saved: str = "",
    tg: str = "",
):
    user_topics = await topic_service.get_user_topics(session, user.id)
    can_teach = [ut for ut in user_topics if ut.kind == TopicKind.can_teach]
    wants_learn = [ut for ut in user_topics if ut.kind == TopicKind.wants_learn]
    balance = await chocolate_service.get_balance(session, user.id)
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "can_teach": can_teach,
            "wants_learn": wants_learn,
            "balance": balance,
            "edu_levels": list(EduLevel),
            "error": error,
            "saved": saved == "1",
            "tg": tg,
            "profile_locked": user_service.is_profile_locked(user),
            "profile_locked_until": user.profile_locked_until,
            # На доску можно только с ≥1 «могу объяснить» и ≥1 «хочу узнать».
            "can_publish_board": bool(can_teach) and bool(wants_learn),
            # Регистрировался по почте (есть email), но ещё не привязал
            # Telegram → предлагаем привязку модалкой, чтобы работал бот.
            "suggest_link_tg": bool(user.email) and not user.telegram_id,
        },
    )


def _parse_edu_level(raw: str) -> EduLevel | None:
    try:
        return EduLevel(raw)
    except ValueError:
        return None


def _locked_redirect(user) -> RedirectResponse | None:
    """Если админ заблокировал правку профиля — вернуть редирект с ошибкой."""
    if user_service.is_profile_locked(user):
        until = user.profile_locked_until.strftime("%d.%m.%Y %H:%M")
        msg = f"Редактирование профиля ограничено администратором до {until} UTC"
        return RedirectResponse(
            url=f"/profile?error={quote(msg)}", status_code=303
        )
    return None


@router.post("/profile")
async def update_profile(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    display_name: str = Form(...),
    bio: str = Form(""),
    show_tg_username: str = Form(""),
    university: str = Form(""),
    course: str = Form(""),
    edu_level: str = Form(""),
):
    if (r := _locked_redirect(user)) is not None:
        return r
    course_val = int(course) if course.isdigit() else None
    level = _parse_edu_level(edu_level)
    # Школьник учится в школе — вуз подставляем сами.
    if level == EduLevel.schoolchild:
        university = "Школа"
    try:
        await user_service.update_profile(
            session,
            user,
            display_name=display_name,
            bio=bio,
            show_tg_username=show_tg_username == "on",
            university=university or None,
            course=course_val,
            edu_level=level,
        )
        await session.commit()
    except ProfanityError as e:
        return RedirectResponse(
            url=f"/profile?error={quote(str(e))}", status_code=303
        )
    return RedirectResponse(url="/profile?saved=1", status_code=303)


@router.post("/profile/email")
async def change_email(
    user: CurrentUser,
    session: SessionDep,
    email: str = Form(...),
):
    """Меняет/добавляет email и отправляет код подтверждения."""
    try:
        await user_service.change_email(session, user, email)
        await session.commit()
    except AuthError as e:
        return RedirectResponse(
            url=f"/profile?error={quote(str(e))}", status_code=303
        )
    # Генерируем код и шлём письмо; gate теперь уведёт на /verify-email.
    try:
        code = await email_verify_service.issue_code(user.id, user.email)
        try:
            await email_service.send_verification_code(user.email, code)
        except email_service.EmailError:
            pass  # покажем страницу подтверждения с возможностью переслать
    except TooSoonError:
        pass
    return RedirectResponse(url="/verify-email", status_code=303)


@router.post("/profile/avatar")
async def upload_avatar(
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),
):
    if (r := _locked_redirect(user)) is not None:
        return r
    try:
        avatar_url = await upload_service.save_avatar(file, user.id)
    except upload_service.UploadError as e:
        return RedirectResponse(
            url=f"/profile?error={quote(str(e))}", status_code=303
        )
    await user_service.update_profile(session, user, avatar_url=avatar_url)
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/avatar/reset")
async def reset_avatar(user: CurrentUser, session: SessionDep):
    """Сброс своего аватара на дефолтный (инициал на градиенте)."""
    if (r := _locked_redirect(user)) is not None:
        return r
    await user_service.reset_avatar(session, user.id)
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/add")
async def add_topic(
    user: CurrentUser,
    session: SessionDep,
    topic_name: str = Form(...),
    kind: str = Form(...),
    level: str = Form(""),
    details: str = Form(""),
    price: str = Form(""),
):
    if (r := _locked_redirect(user)) is not None:
        return r
    lvl = int(level) if level.isdigit() else None
    if lvl is not None:
        lvl = min(max(lvl, 1), 10)
    price_val = int(price) if price.isdigit() else None
    try:
        topic = await topic_service.get_or_create_topic(session, topic_name)
        await topic_service.set_user_topic(
            session,
            user.id,
            topic,
            TopicKind(kind),
            lvl,
            details=details or None,
            price=price_val,
        )
        await session.commit()
    except ProfanityError as e:
        return RedirectResponse(
            url=f"/profile?error={quote(str(e))}", status_code=303
        )
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/{user_topic_id}/price")
async def update_topic_price(
    user: CurrentUser,
    session: SessionDep,
    user_topic_id: int,
    price: str = Form(""),
):
    if (r := _locked_redirect(user)) is not None:
        return r
    price_val = int(price) if price.isdigit() else None
    await topic_service.update_user_topic_price(
        session, user.id, user_topic_id, price_val
    )
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/{user_topic_id}/level")
async def update_topic_level(
    user: CurrentUser,
    session: SessionDep,
    user_topic_id: int,
    level: str = Form(""),
):
    if (r := _locked_redirect(user)) is not None:
        return r
    lvl = int(level) if level.isdigit() else None
    await topic_service.update_user_topic_level(
        session, user.id, user_topic_id, lvl
    )
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/{user_topic_id}/details")
async def update_topic_details(
    user: CurrentUser,
    session: SessionDep,
    user_topic_id: int,
    details: str = Form(""),
):
    if (r := _locked_redirect(user)) is not None:
        return r
    try:
        await topic_service.update_user_topic_details(
            session, user.id, user_topic_id, details or None
        )
        await session.commit()
    except ProfanityError as e:
        return RedirectResponse(
            url=f"/profile?error={quote(str(e))}", status_code=303
        )
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/{user_topic_id}/remove")
async def remove_topic(
    user: CurrentUser, session: SessionDep, user_topic_id: int
):
    if (r := _locked_redirect(user)) is not None:
        return r
    await topic_service.remove_user_topic(session, user.id, user_topic_id)
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/board/toggle")
async def toggle_board(user: CurrentUser, session: SessionDep):
    from app.services import board_service

    if (r := _locked_redirect(user)) is not None:
        return r
    # Публикация возможна только при ≥1 «могу объяснить» и ≥1 «хочу узнать».
    if not user.on_board and not await board_service.can_publish(
        session, user.id
    ):
        msg = (
            "Чтобы выложиться на доску, добавьте хотя бы одну тему "
            "«могу объяснить» и одну «хочу узнать»."
        )
        return RedirectResponse(
            url=f"/profile?error={quote(msg)}", status_code=303
        )
    await board_service.toggle_board(session, user)
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.get("/u/{user_id}", response_class=HTMLResponse)
async def public_profile(
    request: Request,
    user: CurrentUserOptional,
    session: SessionDep,
    user_id: int,
):
    profile_user = await user_service.get_by_id(session, user_id)
    if profile_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user_topics = await topic_service.get_user_topics(session, user_id)
    can_teach = [ut for ut in user_topics if ut.kind == TopicKind.can_teach]
    wants_learn = [ut for ut in user_topics if ut.kind == TopicKind.wants_learn]
    return templates.TemplateResponse(
        request,
        "public_profile.html",
        {
            "user": user,
            "profile_user": profile_user,
            "can_teach": can_teach,
            "wants_learn": wants_learn,
        },
    )


@router.post("/profile/link-telegram")
async def link_telegram(user: CurrentUser):
    """Генерирует deep-link для привязки Telegram."""
    from app.core.config import settings

    code = await linking_service.generate_link_code(user.id)
    url = f"https://t.me/{settings.bot_username}?start={code}"
    return RedirectResponse(url=url, status_code=303)


@router.post("/profile/unlink-telegram")
async def unlink_telegram(user: CurrentUser, session: SessionDep):
    """Отвязывает Telegram от аккаунта.

    Требует наличия email — иначе нарушится CHECK ck_user_has_login_method
    (у пользователя должен остаться хотя бы один способ входа).
    """
    if not user.email:
        return RedirectResponse(url="/profile?tg=need_email", status_code=303)
    user.telegram_id = None
    user.telegram_username = None
    await session.commit()
    return RedirectResponse(url="/profile?tg=unlinked", status_code=303)
