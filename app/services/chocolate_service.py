from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chocolate import ChocolateReason, ChocolateTransaction
from app.models.user import User

# Настройки экономики.
_SIGNUP_BONUS = 5
_WEEKLY_AMOUNT = 1
_WEEKLY_PERIOD = timedelta(days=7)
# Максимум недель, которые догоняем за один заход (защита от накрутки при
# долгом отсутствии).
_WEEKLY_MAX_CATCHUP = 4


class NotEnoughChocolates(Exception):
    """Недостаточно шоколадок для списания."""


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


async def spend(
    session: AsyncSession,
    user_id: int,
    amount: int,
    reason: ChocolateReason,
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> ChocolateTransaction:
    """Списывает шоколадки: транзакция с отрицательной суммой + кэш-баланс.

    Бросает NotEnoughChocolates, если баланс меньше amount.
    """
    if amount <= 0:
        raise ValueError("amount должен быть положительным")

    user = await session.get(User, user_id)
    if user is None or user.chocolate_balance < amount:
        raise NotEnoughChocolates("Недостаточно шоколадок")

    tx = ChocolateTransaction(
        from_user_id=user_id,
        to_user_id=user_id,
        amount=-amount,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    session.add(tx)
    user.chocolate_balance -= amount
    await session.flush()
    return tx


async def grant_weekly_if_due(session: AsyncSession, user: User) -> bool:
    """Ленивая еженедельная выдача (планировщика нет).

    Начисляет по +1 за каждую прошедшую неделю с момента last_weekly_at
    (максимум _WEEKLY_MAX_CATCHUP), обновляет last_weekly_at. Первый заход
    просто фиксирует отметку без начисления. Возвращает True, если что-то
    изменилось в БД (нужно закоммитить в вызывающем коде).
    """
    now = datetime.now(timezone.utc)

    if user.last_weekly_at is None:
        # Первый раз — только ставим отметку, чтобы не выдать за «всю историю».
        user.last_weekly_at = now
        await session.flush()
        return True

    last = user.last_weekly_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    elapsed = now - last
    weeks = int(elapsed // _WEEKLY_PERIOD)
    if weeks <= 0:
        return False

    weeks = min(weeks, _WEEKLY_MAX_CATCHUP)
    await award(
        session,
        to_user_id=user.id,
        amount=_WEEKLY_AMOUNT * weeks,
        reason=ChocolateReason.weekly,
        ref_type="weekly",
    )
    user.last_weekly_at = last + _WEEKLY_PERIOD * weeks
    await session.flush()
    return True


async def award_signup_bonus(
    session: AsyncSession, user_id: int
) -> ChocolateTransaction:
    """Стартовый бонус при регистрации: +5 шоколадок."""
    return await award(
        session,
        to_user_id=user_id,
        amount=_SIGNUP_BONUS,
        reason=ChocolateReason.signup,
        ref_type="signup",
    )


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
