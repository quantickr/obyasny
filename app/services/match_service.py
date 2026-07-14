from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.match import Match, MatchStatus
from app.models.topic import Topic, TopicKind, UserTopic
from app.models.user import User


@dataclass
class MatchCandidate:
    partner: User
    i_teach_topic: Topic  # что текущий пользователь объясняет партнёру
    partner_teaches_topic: Topic  # что партнёр объясняет мне
    score: float


async def find_mutual_matches(
    session: AsyncSession, user_id: int, limit: int = 20
) -> list[MatchCandidate]:
    """Двусторонний подбор: я учу партнёра теме t1, партнёр учит меня теме t2.

    t1 ∈ (my can_teach) ∩ (partner wants_learn)
    t2 ∈ (partner can_teach) ∩ (my wants_learn)
    """
    my_teach = aliased(UserTopic)  # я умею объяснить
    partner_learn = aliased(UserTopic)  # партнёр хочет узнать это же
    partner_teach = aliased(UserTopic)  # партнёр умеет объяснить
    my_learn = aliased(UserTopic)  # я хочу узнать это же
    t1 = aliased(Topic)
    t2 = aliased(Topic)

    stmt = (
        select(
            partner_learn.user_id.label("partner_id"),
            my_teach.topic_id.label("i_teach_topic_id"),
            partner_teach.topic_id.label("partner_teaches_topic_id"),
            t1,
            t2,
        )
        .select_from(my_teach)
        .join(
            partner_learn,
            and_(
                partner_learn.topic_id == my_teach.topic_id,
                partner_learn.kind == TopicKind.wants_learn,
            ),
        )
        .join(
            partner_teach,
            and_(
                partner_teach.user_id == partner_learn.user_id,
                partner_teach.kind == TopicKind.can_teach,
            ),
        )
        .join(
            my_learn,
            and_(
                my_learn.topic_id == partner_teach.topic_id,
                my_learn.kind == TopicKind.wants_learn,
                my_learn.user_id == user_id,
            ),
        )
        .join(t1, t1.id == my_teach.topic_id)
        .join(t2, t2.id == partner_teach.topic_id)
        .where(
            my_teach.user_id == user_id,
            my_teach.kind == TopicKind.can_teach,
            partner_learn.user_id != user_id,
        )
    )

    rows = (await session.execute(stmt)).all()

    # Агрегируем по партнёру: score растёт с числом взаимных пар тем.
    seen: dict[tuple[int, int, int], MatchCandidate] = {}
    partner_pair_count: dict[int, int] = {}
    partner_ids = {r.partner_id for r in rows}
    partners = {
        u.id: u
        for u in await session.scalars(
            select(User).where(User.id.in_(partner_ids))
        )
    }

    for r in rows:
        partner_pair_count[r.partner_id] = (
            partner_pair_count.get(r.partner_id, 0) + 1
        )

    for r in rows:
        key = (r.partner_id, r.i_teach_topic_id, r.partner_teaches_topic_id)
        if key in seen:
            continue
        partner = partners.get(r.partner_id)
        if partner is None:
            continue
        score = 2.0 * partner_pair_count[r.partner_id]
        seen[key] = MatchCandidate(
            partner=partner,
            i_teach_topic=r[3],
            partner_teaches_topic=r[4],
            score=score,
        )

    candidates = sorted(seen.values(), key=lambda c: c.score, reverse=True)
    return candidates[:limit]


async def save_suggested_match(
    session: AsyncSession,
    user_id: int,
    candidate: MatchCandidate,
) -> Match:
    """Сохраняет предложенную пару с нормализацией user_a_id < user_b_id."""
    partner_id = candidate.partner.id
    if user_id < partner_id:
        a_id, b_id = user_id, partner_id
        a_teaches = candidate.i_teach_topic.id
        b_teaches = candidate.partner_teaches_topic.id
    else:
        a_id, b_id = partner_id, user_id
        a_teaches = candidate.partner_teaches_topic.id
        b_teaches = candidate.i_teach_topic.id

    existing = await session.scalar(
        select(Match).where(
            Match.user_a_id == a_id,
            Match.user_b_id == b_id,
            Match.a_teaches_topic_id == a_teaches,
            Match.b_teaches_topic_id == b_teaches,
        )
    )
    if existing:
        return existing

    match = Match(
        user_a_id=a_id,
        user_b_id=b_id,
        a_teaches_topic_id=a_teaches,
        b_teaches_topic_id=b_teaches,
        score=candidate.score,
        status=MatchStatus.suggested,
    )
    session.add(match)
    await session.flush()
    return match
