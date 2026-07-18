from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.report import ReportContext
from app.services import report_service
from app.services.report_service import ReportError
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/my-reports", response_class=HTMLResponse)
async def my_reports(
    request: Request, user: CurrentUser, session: SessionDep
):
    """Жалобы, отправленные текущим пользователем, со статусом и ответом админа."""
    reports = await report_service.list_reports_by_reporter(session, user.id)
    return templates.TemplateResponse(
        request,
        "my_reports.html",
        {"user": user, "reports": reports},
    )


@router.post("/report")
async def submit_report(
    user: CurrentUser,
    session: SessionDep,
    reported_user_id: int = Form(...),
    context: str = Form("board"),
    reason: str = Form(""),
    chat_id: int | None = Form(None),
    next_url: str = Form("/board"),
):
    """Жалоба на пользователя (с доски / профиля / из чата)."""
    try:
        context_enum = ReportContext(context)
    except ValueError:
        context_enum = ReportContext.board
    try:
        await report_service.create_report(
            session,
            reporter_id=user.id,
            reported_user_id=reported_user_id,
            context=context_enum,
            reason=reason,
            chat_id=chat_id,
        )
        await session.commit()
    except ReportError:
        pass
    # Защита от открытого редиректа: разрешаем только внутренние пути.
    target = next_url if next_url.startswith("/") else "/board"
    return RedirectResponse(url=target, status_code=303)
