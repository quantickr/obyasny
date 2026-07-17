from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.profanity import ProfanityError
from app.models.topic import TopicKind
from app.models.user import EduLevel
from app.services import (
    chocolate_service,
    linking_service,
    topic_service,
    upload_service,
    user_service,
)
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
        },
    )


def _parse_edu_level(raw: str) -> EduLevel | None:
    try:
        return EduLevel(raw)
    except ValueError:
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


@router.post("/profile/avatar")
async def upload_avatar(
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),
):
    try:
        avatar_url = await upload_service.save_avatar(file, user.id)
    except upload_service.UploadError as e:
        return RedirectResponse(
            url=f"/profile?error={quote(str(e))}", status_code=303
        )
    await user_service.update_profile(session, user, avatar_url=avatar_url)
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
):
    lvl = int(level) if level.isdigit() else None
    if lvl is not None:
        lvl = min(max(lvl, 1), 10)
    try:
        topic = await topic_service.get_or_create_topic(session, topic_name)
        await topic_service.set_user_topic(
            session,
            user.id,
            topic,
            TopicKind(kind),
            lvl,
            details=details or None,
        )
        await session.commit()
    except ProfanityError as e:
        return RedirectResponse(
            url=f"/profile?error={quote(str(e))}", status_code=303
        )
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/{user_topic_id}/level")
async def update_topic_level(
    user: CurrentUser,
    session: SessionDep,
    user_topic_id: int,
    level: str = Form(""),
):
    lvl = int(level) if level.isdigit() else None
    await topic_service.update_user_topic_level(
        session, user.id, user_topic_id, lvl
    )
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/{user_topic_id}/remove")
async def remove_topic(
    user: CurrentUser, session: SessionDep, user_topic_id: int
):
    await topic_service.remove_user_topic(session, user.id, user_topic_id)
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/board/toggle")
async def toggle_board(user: CurrentUser, session: SessionDep):
    from app.services import board_service

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
