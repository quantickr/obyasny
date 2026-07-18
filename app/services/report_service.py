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
    session: AsyncSession,
    report_id: int,
    status: ReportStatus,
    reply: str | None = None,
    admin_id: int | None = None,
) -> Report | None:
    """Меняет статус жалобы. Возвращает Report только если статус реально
    сменился с open (для однократного применения побочных эффектов, например
    начисления рейтинга). Повторный вызов на уже закрытой жалобе вернёт None.

    reply — текстовый ответ админа репортёру, admin_id — кто закрыл жалобу.
    """
    report = await session.get(Report, report_id)
    if report is None:
        return None
    if report.status != ReportStatus.open:
        return None  # уже обработана — не применяем эффекты повторно
    report.status = status
    report.resolved_at = datetime.now(timezone.utc)
    report.admin_reply = (reply or "").strip() or None
    report.resolved_by = admin_id
    await session.flush()
    return report


async def resolve(
    session: AsyncSession,
    report_id: int,
    reply: str | None = None,
    admin_id: int | None = None,
) -> Report | None:
    """Признаёт жалобу обоснованной. Возвращает Report при первом разрешении
    (для начисления рейтинга виноватому/репортёру), иначе None."""
    return await _set_status(
        session, report_id, ReportStatus.resolved, reply, admin_id
    )


async def dismiss(
    session: AsyncSession,
    report_id: int,
    reply: str | None = None,
    admin_id: int | None = None,
) -> Report | None:
    return await _set_status(
        session, report_id, ReportStatus.dismissed, reply, admin_id
    )


async def list_reports_by_reporter(
    session: AsyncSession, reporter_id: int
) -> list[Report]:
    """Жалобы, отправленные пользователем (для страницы «Мои жалобы»)."""
    stmt = (
        select(Report)
        .where(Report.reporter_id == reporter_id)
        .options(selectinload(Report.reported))
        .order_by(Report.created_at.desc())
    )
    return list(await session.scalars(stmt))


async def open_count(session: AsyncSession) -> int:
    stmt = select(func.count(Report.id)).where(
        Report.status == ReportStatus.open
    )
    return int(await session.scalar(stmt) or 0)


async def resolved_counts_by_users(
    session: AsyncSession, user_ids: list[int]
) -> dict[int, int]:
    """Сколько подтверждённых (resolved) жалоб на каждого из user_ids.
    Пользователи без resolved-жалоб в словаре отсутствуют (get → 0)."""
    if not user_ids:
        return {}
    stmt = (
        select(Report.reported_user_id, func.count(Report.id))
        .where(
            Report.reported_user_id.in_(user_ids),
            Report.status == ReportStatus.resolved,
        )
        .group_by(Report.reported_user_id)
    )
    rows = await session.execute(stmt)
    return {uid: cnt for uid, cnt in rows.all()}
