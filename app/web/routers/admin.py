from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.profanity import ProfanityError
from app.models.report import ReportStatus
from app.models.topic import TopicKind
from app.models.user import EduLevel
from app.services import report_service, topic_service, user_service
from app.web.dependencies import CurrentAdmin, SessionDep
from app.web.templating import templates

router = APIRouter(prefix="/admin")


#: Пресеты длительности наказаний.
_PRESETS = {
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _parse_until(preset: str, amount: str, unit: str) -> datetime | None:
    """Вычисляет дату окончания наказания.

    preset: "1h"/"1d"/"7d"/"30d" → фикс. срок; "forever" → None (бессрочно);
    "custom" → now + amount*(hours|days).
    """
    now = datetime.now(timezone.utc)
    if preset == "forever":
        return None
    if preset in _PRESETS:
        return now + _PRESETS[preset]
    if preset == "custom":
        try:
            n = int(amount)
        except (TypeError, ValueError):
            n = 0
        n = max(1, min(n, 3650))
        delta = timedelta(days=n) if unit == "days" else timedelta(hours=n)
        return now + delta
    # Неизвестный пресет — трактуем как сутки (безопасный дефолт).
    return now + timedelta(days=1)


@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request, admin: CurrentAdmin, session: SessionDep):
    users_total = await user_service.count_users(session)
    open_reports = await report_service.open_count(session)
    recent = await report_service.list_reports(session, ReportStatus.open)
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "user": admin,
            "users_total": users_total,
            "open_reports": open_reports,
            "recent": recent[:10],
        },
    )


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    admin: CurrentAdmin,
    session: SessionDep,
    status: str = "open",
):
    try:
        status_enum = ReportStatus(status)
    except ValueError:
        status_enum = ReportStatus.open
    reports = await report_service.list_reports(session, status_enum)
    return templates.TemplateResponse(
        request,
        "admin/reports.html",
        {
            "user": admin,
            "reports": reports,
            "status": status_enum.value,
        },
    )


@router.post("/reports/{report_id}/resolve")
async def resolve_report(
    report_id: int, admin: CurrentAdmin, session: SessionDep
):
    await report_service.resolve(session, report_id)
    await session.commit()
    return RedirectResponse(url="/admin/reports", status_code=303)


@router.post("/reports/{report_id}/dismiss")
async def dismiss_report(
    report_id: int, admin: CurrentAdmin, session: SessionDep
):
    await report_service.dismiss(session, report_id)
    await session.commit()
    return RedirectResponse(url="/admin/reports", status_code=303)


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    admin: CurrentAdmin,
    session: SessionDep,
    q: str = "",
):
    users = await user_service.list_users(session, q or None)
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {"user": admin, "users": users, "q": q},
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    request: Request, user_id: int, admin: CurrentAdmin, session: SessionDep
):
    target = await user_service.get_by_id(session, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user_topics = await topic_service.get_user_topics(session, user_id)
    can_teach = [ut for ut in user_topics if ut.kind == TopicKind.can_teach]
    wants_learn = [ut for ut in user_topics if ut.kind == TopicKind.wants_learn]
    return templates.TemplateResponse(
        request,
        "admin/user_detail.html",
        {
            "user": admin,
            "target": target,
            "can_teach": can_teach,
            "wants_learn": wants_learn,
            "edu_levels": list(EduLevel),
            "now": datetime.now(timezone.utc),
            "is_muted": user_service.is_muted(target),
            "is_locked": user_service.is_profile_locked(target),
        },
    )


@router.post("/users/{user_id}/profile")
async def edit_user_profile(
    user_id: int,
    admin: CurrentAdmin,
    session: SessionDep,
    display_name: str = Form(...),
    university: str = Form(""),
    course: str = Form(""),
    edu_level: str = Form(""),
    bio: str = Form(""),
):
    target = await user_service.get_by_id(session, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    try:
        level = EduLevel(edu_level)
    except ValueError:
        level = None
    if level == EduLevel.schoolchild:
        university = "Школа"
    course_val = int(course) if course.isdigit() else None
    try:
        await user_service.update_profile(
            session,
            target,
            display_name=display_name,
            bio=bio,
            university=university or None,
            course=course_val,
            edu_level=level,
        )
        await session.commit()
    except ProfanityError:
        pass  # админ вводит данные сам — просто игнорируем нецензурное
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/board/off")
async def user_board_off(
    user_id: int, admin: CurrentAdmin, session: SessionDep
):
    await user_service.admin_set_board(session, user_id, False)
    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/topics/add")
async def user_topic_add(
    user_id: int,
    admin: CurrentAdmin,
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
            session, user_id, topic, TopicKind(kind), lvl,
            details=details or None,
        )
        await session.commit()
    except (ProfanityError, ValueError):
        pass
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/topics/{ut_id}/remove")
async def user_topic_remove(
    user_id: int, ut_id: int, admin: CurrentAdmin, session: SessionDep
):
    await topic_service.remove_user_topic(session, user_id, ut_id)
    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


# --- Наказания со сроком (бан / мут / блок профиля) ---


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    admin: CurrentAdmin,
    session: SessionDep,
    preset: str = Form("forever"),
    amount: str = Form(""),
    unit: str = Form("hours"),
):
    if user_id != admin.id:  # нельзя забанить себя
        await user_service.set_ban(
            session, user_id, _parse_until(preset, amount, unit)
        )
        await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    await user_service.clear_ban(session, user_id)
    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/mute")
async def mute_user(
    user_id: int,
    admin: CurrentAdmin,
    session: SessionDep,
    preset: str = Form("1d"),
    amount: str = Form(""),
    unit: str = Form("hours"),
):
    if user_id != admin.id:
        await user_service.set_mute(
            session, user_id, _parse_until(preset, amount, unit)
        )
        await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/unmute")
async def unmute_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    await user_service.clear_mute(session, user_id)
    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/lock")
async def lock_user(
    user_id: int,
    admin: CurrentAdmin,
    session: SessionDep,
    preset: str = Form("7d"),
    amount: str = Form(""),
    unit: str = Form("hours"),
):
    if user_id != admin.id:
        await user_service.set_profile_lock(
            session, user_id, _parse_until(preset, amount, unit)
        )
        await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/unlock")
async def unlock_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    await user_service.clear_profile_lock(session, user_id)
    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)
