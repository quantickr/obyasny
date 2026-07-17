from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.report import Report, ReportContext, ReportStatus


class ReportError(Exception):
    pass


async def create_report(
    session: AsyncSession,
    reporter_id: int,
    reported_user_id: int,
    context: ReportContext,
    reason: str | None = None,
    chat_id: int | None = None,
) -> Report:
    """Создаёт жалобу. Нельзя жаловаться на себя; не плодим дубли open-жалоб
    на ту же пару в том же контексте."""
    if reporter_id == reported_user_id:
        raise ReportError("Нельзя пожаловаться на самого себя")

    existing = await session.scalar(
        select(Report).where(
            Report.reporter_id == reporter_id,
            Report.reported_user_id == reported_user_id,
            Report.context == context,
            Report.status == ReportStatus.open,
        )
    )
    if existing is not None:
        return existing  # идемпотентно: жалоба уже на рассмотрении

    report = Report(
        reporter_id=reporter_id,
        reported_user_id=reported_user_id,
        context=context,
        reason=(reason or "").strip() or None,
        chat_id=chat_id,
        status=ReportStatus.open,
    )
    session.add(report)
    await session.flush()
    return report


async def list_reports(
    session: AsyncSession,
    status: ReportStatus = ReportStatus.open,
    context: ReportContext | None = None,
) -> list[Report]:
    stmt = (
        select(Report)
        .where(Report.status == status)
        .options(
            selectinload(Report.reporter),
            selectinload(Report.reported),
        )
        .order_by(Report.created_at.desc())
    )
    if context is not None:
        stmt = stmt.where(Report.context == context)
    return list(await session.scalars(stmt))


async def _set_status(
    session: AsyncSession, report_id: int, status: ReportStatus
) -> None:
    report = await session.get(Report, report_id)
    if report is None:
        return
    report.status = status
    report.resolved_at = datetime.now(timezone.utc)
    await session.flush()


async def resolve(session: AsyncSession, report_id: int) -> None:
    await _set_status(session, report_id, ReportStatus.resolved)


async def dismiss(session: AsyncSession, report_id: int) -> None:
    await _set_status(session, report_id, ReportStatus.dismissed)


async def open_count(session: AsyncSession) -> int:
    stmt = select(func.count(Report.id)).where(
        Report.status == ReportStatus.open
    )
    return int(await session.scalar(stmt) or 0)
