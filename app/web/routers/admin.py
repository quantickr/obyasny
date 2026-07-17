from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.report import ReportStatus
from app.services import report_service, user_service
from app.web.dependencies import CurrentAdmin, SessionDep
from app.web.templating import templates

router = APIRouter(prefix="/admin")


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


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    if user_id != admin.id:  # нельзя забанить себя
        await user_service.set_banned(session, user_id, True)
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: int, admin: CurrentAdmin, session: SessionDep):
    await user_service.set_banned(session, user_id, False)
    await session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)
