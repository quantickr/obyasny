from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.topic import TopicKind
from app.services import chocolate_service, linking_service, topic_service, user_service
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request, user: CurrentUser, session: SessionDep
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
        },
    )


@router.post("/profile")
async def update_profile(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    display_name: str = Form(...),
    bio: str = Form(""),
    show_tg_username: str = Form(""),
):
    await user_service.update_profile(
        session,
        user,
        display_name=display_name,
        bio=bio,
        show_tg_username=show_tg_username == "on",
    )
    await session.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/topics/add")
async def add_topic(
    user: CurrentUser,
    session: SessionDep,
    topic_name: str = Form(...),
    kind: str = Form(...),
    level: str = Form(""),
):
    topic = await topic_service.get_or_create_topic(session, topic_name)
    lvl = int(level) if level.isdigit() else None
    if lvl is not None:
        lvl = min(max(lvl, 1), 10)
    await topic_service.set_user_topic(
        session, user.id, topic, TopicKind(kind), lvl
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


@router.post("/profile/link-telegram")
async def link_telegram(user: CurrentUser):
    """Генерирует deep-link для привязки Telegram."""
    from app.core.config import settings

    code = await linking_service.generate_link_code(user.id)
    url = f"https://t.me/{settings.bot_username}?start={code}"
    return RedirectResponse(url=url, status_code=303)
