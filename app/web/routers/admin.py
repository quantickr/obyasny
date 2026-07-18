from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.profanity import ProfanityError
from app.models.report import ReportContext, ReportStatus
from app.models.topic import TopicKind
from app.models.user import EduLevel, User
from app.services import (
    chat_service,
    report_service,
    request_service,
    topic_service,
    user_service,
)
from app.services.request_service import RequestError
from app.web.dependencies import (
    CurrentAdmin,
    CurrentSuperadmin,
    RequireAdminAccess,
    SessionDep,
)
from app.web.templating import templates

router = APIRouter(prefix="/admin")


def _require(admin: User, attr: str) -> None:
    """Точечная проверка права. Суперадмин обходит любые проверки."""
    if not (admin.is_superadmin or getattr(admin, attr, False)):
        raise RequireAdminAccess()


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
    open_disputes = len(await request_service.list_disputed(session))
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "user": admin,
            "users_total": users_total,
            "open_reports": open_reports,
            "open_disputes": open_disputes,
            "recent": recent[:10],
        },
    )


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    admin: CurrentAdmin,
    session: SessionDep,
    status: str = "open",
    context: str = "",
):
    try:
        status_enum = ReportStatus(status)
    except ValueError:
        status_enum = ReportStatus.open
    try:
        context_enum = ReportContext(context) if context else None
    except ValueError:
        context_enum = None
    reports = await report_service.list_reports(
        session, status_enum, context_enum
    )
    # Сколько ранее подтверждённых жалоб было на каждого нарушителя.
    resolved_counts = await report_service.resolved_counts_by_users(
        session, [r.reported_user_id for r in reports]
    )
    # Для мини-панелей: темы reported (жалобы на доску) и статус мута (чат).
    topics_by_user: dict[int, dict[str, list]] = {}
    muted_by_user: dict[int, bool] = {}
    for r in reports:
        uid = r.reported_user_id
        if r.context == ReportContext.board and uid not in topics_by_user:
            uts = await topic_service.get_user_topics(session, uid)
            topics_by_user[uid] = {
                "can_teach": [
                    ut for ut in uts if ut.kind == TopicKind.can_teach
                ],
                "wants_learn": [
                    ut for ut in uts if ut.kind == TopicKind.wants_learn
                ],
            }
        if r.context == ReportContext.chat and uid not in muted_by_user:
            target = await user_service.get_by_id(session, uid)
            muted_by_user[uid] = (
                user_service.is_muted(target) if target else False
            )
    return templates.TemplateResponse(
        request,
        "admin/reports.html",
        {
            "user": admin,
            "reports": reports,
            "status": status_enum.value,
            "context": context_enum.value if context_enum else "",
            "topics_by_user": topics_by_user,
            "muted_by_user": muted_by_user,
            "resolved_counts": resolved_counts,
        },
    )


@router.post("/reports/{report_id}/resolve")
async def resolve_report(
    report_id: int,
    admin: CurrentAdmin,
    session: SessionDep,
    reply: str = Form(""),
):
    _require(admin, "can_manage_reports")
    # Доказанная жалоба меняет рейтинг: виноватому −5, репортёру +1.
    # resolve() возвращает Report только при первом разрешении (open→resolved),
    # поэтому повторное «Разрешить» рейтинг не начислит дважды.
    report = await report_service.resolve(
        session, report_id, reply=reply, admin_id=admin.id
    )
    if report is not None:
        guilty = await session.get(User, report.reported_user_id)
        reporter = await session.get(User, report.reporter_id)
        if guilty is not None:
            guilty.rating -= 5
        if reporter is not None:
            reporter.rating += 1
    await session.commit()
    return RedirectResponse(url="/admin/reports", status_code=303)


@router.post("/reports/{report_id}/dismiss")
async def dismiss_report(
    report_id: int,
    admin: CurrentAdmin,
    session: SessionDep,
    reply: str = Form(""),
):
    _require(admin, "can_manage_reports")
    await report_service.dismiss(
        session, report_id, reply=reply, admin_id=admin.id
    )
    await session.commit()
    return RedirectResponse(url="/admin/reports", status_code=303)


@router.get("/chat/{chat_id}", response_class=HTMLResponse)
async def admin_chat_view(
    request: Request, chat_id: int, admin: CurrentAdmin, session: SessionDep
):
    """Read-only просмотр любого чата админом (для разбора жалоб/споров)."""
    _require(admin, "can_manage_reports")
    chat = await chat_service.get_chat(session, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Чат не найден")
    u1 = await user_service.get_by_id(session, chat.user1_id)
    u2 = await user_service.get_by_id(session, chat.user2_id)
    messages = await chat_service.get_messages(session, chat_id)
    return templates.TemplateResponse(
        request,
        "admin/chat_view.html",
        {
            "user": admin,
            "chat": chat,
            "u1": u1,
            "u2": u2,
            "messages": messages,
        },
    )


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
    _require(admin, "can_edit_profiles")
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


@router.post("/users/{user_id}/delete")
async def delete_user_admin(
    user_id: int, admin: CurrentSuperadmin, session: SessionDep
):
    """Удаление чужого аккаунта (только суперадмин).

    Нельзя удалить себя и других суперадминов.
    """
    if user_id == admin.id:
        return RedirectResponse(
            url=f"/admin/users/{user_id}", status_code=303
        )
    target = await user_service.get_by_id(session, user_id)
    if target is None or target.is_superadmin:
        return RedirectResponse(url="/admin/users", status_code=303)
    await user_service.delete_user(session, user_id)
    await session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/board/off")
async def user_board_off(
    user_id: int, admin: CurrentAdmin, session: SessionDep
):
    _require(admin, "can_edit_profiles")
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
    price: str = Form(""),
):
    _require(admin, "can_edit_profiles")
    lvl = int(level) if level.isdigit() else None
    if lvl is not None:
        lvl = min(max(lvl, 1), 10)
    price_val = int(price) if price.isdigit() else None
    try:
        topic = await topic_service.get_or_create_topic(session, topic_name)
        await topic_service.set_user_topic(
            session, user_id, topic, TopicKind(kind), lvl,
            details=details or None,
            price=price_val,
        )
        await session.commit()
    except (ProfanityError, ValueError):
        pass
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/topics/{ut_id}/remove")
async def user_topic_remove(
    user_id: int, ut_id: int, admin: CurrentAdmin, session: SessionDep
):
    _require(admin, "can_edit_profiles")
    await topic_service.remove_user_topic(session, user_id, ut_id)
    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/avatar/reset")
async def reset_user_avatar(
    user_id: int, admin: CurrentAdmin, session: SessionDep
):
    """Сброс аватара пользователя на дефолтный (право can_edit_profiles)."""
    _require(admin, "can_edit_profiles")
    await user_service.reset_avatar(session, user_id)
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
    _require(admin, "can_punish")
    if user_id != admin.id:  # нельзя забанить себя
        await user_service.set_ban(
            session, user_id, _parse_until(preset, amount, unit)
        )
        await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    _require(admin, "can_punish")
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
    _require(admin, "can_punish")
    if user_id != admin.id:
        await user_service.set_mute(
            session, user_id, _parse_until(preset, amount, unit)
        )
        await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/unmute")
async def unmute_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    _require(admin, "can_punish")
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
    _require(admin, "can_punish")
    if user_id != admin.id:
        await user_service.set_profile_lock(
            session, user_id, _parse_until(preset, amount, unit)
        )
        await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/unlock")
async def unlock_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    _require(admin, "can_punish")
    await user_service.clear_profile_lock(session, user_id)
    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


# --- Управление администраторами (только суперадмин) ---


@router.get("/admins", response_class=HTMLResponse)
async def admins_page(
    request: Request, admin: CurrentSuperadmin, session: SessionDep
):
    """Список администраторов + управление их правами (только суперадмин)."""
    admins = await user_service.list_admins(session)
    return templates.TemplateResponse(
        request,
        "admin/admins.html",
        {"user": admin, "admins": admins},
    )


@router.post("/users/{user_id}/rights")
async def set_user_rights(
    user_id: int,
    admin: CurrentSuperadmin,
    session: SessionDep,
    is_admin: str = Form(""),
    can_manage_reports: str = Form(""),
    can_punish: str = Form(""),
    can_edit_profiles: str = Form(""),
):
    """Назначение прав администратора (только суперадмин).

    Self-guard: суперадмин не может разжаловать сам себя.
    """
    if user_id == admin.id:
        return RedirectResponse(url="/admin/admins", status_code=303)
    await user_service.set_admin_rights(
        session,
        user_id,
        is_admin=bool(is_admin),
        can_manage_reports=bool(can_manage_reports),
        can_punish=bool(can_punish),
        can_edit_profiles=bool(can_edit_profiles),
    )
    await session.commit()
    return RedirectResponse(url="/admin/admins", status_code=303)


# --- Споры об отмене объяснения (задача 8) ---


@router.get("/disputes", response_class=HTMLResponse)
async def disputes_page(
    request: Request, admin: CurrentAdmin, session: SessionDep
):
    """Заявки, где объясняющий отклонил отмену — спор на разбор админом."""
    _require(admin, "can_manage_reports")
    disputes = await request_service.list_disputed(session)
    return templates.TemplateResponse(
        request,
        "admin/disputes.html",
        {"user": admin, "disputes": disputes},
    )


@router.post("/disputes/{request_id}/resolve")
async def resolve_dispute(
    request_id: int,
    admin: CurrentAdmin,
    session: SessionDep,
    action: str = Form("cancel"),
):
    """Разбор спора: action=cancel → отмена (возврат отправителю),
    action=complete → завершить в пользу объясняющего."""
    _require(admin, "can_manage_reports")
    try:
        await request_service.admin_resolve_dispute(
            session, request_id, cancel=(action == "cancel")
        )
        await session.commit()
    except RequestError:
        pass
    return RedirectResponse(url="/admin/disputes", status_code=303)
