from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chocolate import ChocolateReason, ChocolateTransaction
from app.models.user import User


async def award(
    session: AsyncSession,
    to_user_id: int,
    amount: int,
    reason: ChocolateReason,
    from_user_id: int | None = None,
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> ChocolateTransaction:
    """Начисляет шоколадки: пишет транзакцию + обновляет кэш-баланс."""
    if amount <= 0:
        raise ValueError("amount должен быть положительным")

    tx = ChocolateTransaction(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        amount=amount,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    session.add(tx)

    user = await session.get(User, to_user_id)
    if user:
        user.chocolate_balance += amount
    await session.flush()
    return tx


async def get_balance(session: AsyncSession, user_id: int) -> int:
    user = await session.get(User, user_id)
    return user.chocolate_balance if user else 0


async def history(
    session: AsyncSession, user_id: int, limit: int = 50
) -> list[ChocolateTransaction]:
    stmt = (
        select(ChocolateTransaction)
        .where(ChocolateTransaction.to_user_id == user_id)
        .order_by(ChocolateTransaction.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))
