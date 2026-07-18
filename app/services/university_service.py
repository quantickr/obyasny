"""Поиск вузов для автоподсказок (по названию, сокращениям, с учётом
популярности и лёгких опечаток).

Данные — статический справочник `app/data/universities.py` (в памяти).
Поле вуза допускает свободный ввод, здесь только подсказки.

Ранжирование совпадений (по убыванию приоритета):
1. префикс названия/алиаса совпал с запросом;
2. запрос — подстрока названия/алиаса;
3. нечёткое совпадение (difflib) — ловит лёгкие опечатки.
Внутри одного приоритета — по популярности (порядок в справочнике).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.data.universities import UNIVERSITIES


def _normalize(text: str) -> str:
    """Нижний регистр, ё→е, схлопывание не-буквенно-цифровых в пробел."""
    s = text.lower().replace("ё", "е").strip()
    s = re.sub(r"[^0-9a-zа-я]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Предрассчитанный индекс: (полное_имя, ранг, нормализованные ключи поиска).
# Ключи = нормализованные название + все алиасы.
_INDEX: list[tuple[str, int, list[str]]] = []
for _rank, (_name, _aliases) in enumerate(UNIVERSITIES):
    _keys = [_normalize(_name)] + [_normalize(a) for a in _aliases]
    _keys = [k for k in _keys if k]
    _INDEX.append((_name, _rank, _keys))

# Порог нечёткого совпадения (0..1). Ниже — считаем несовпадением.
_FUZZY_THRESHOLD = 0.72


def _best_match_priority(query: str, keys: list[str]) -> int | None:
    """Возвращает приоритет совпадения запроса с ключами вуза.

    0 — префикс, 1 — подстрока, 2 — нечёткое; None — не совпало.
    Меньше = лучше.
    """
    prefix = False
    substring = False
    fuzzy = False
    for key in keys:
        if key.startswith(query):
            prefix = True
            break
        if query in key:
            substring = True
        elif not substring:
            # Нечёткое сравнение только с ключами близкой длины —
            # чтобы «мгу» не «подходил» к длинным названиям по буквам.
            if abs(len(key) - len(query)) <= max(3, len(query) // 2):
                ratio = SequenceMatcher(None, query, key).ratio()
                if ratio >= _FUZZY_THRESHOLD:
                    fuzzy = True
    if prefix:
        return 0
    if substring:
        return 1
    if fuzzy:
        return 2
    return None


# Точное соответствие «нормализованный ключ → каноничное название вуза».
# Строится один раз: для каждого вуза его название и все алиасы указывают
# на каноничное название из справочника.
_CANONICAL_BY_KEY: dict[str, str] = {}
for _name, _rank, _keys in _INDEX:
    for _key in _keys:
        _CANONICAL_BY_KEY.setdefault(_key, _name)


def canonical(value: str | None) -> str | None:
    """Приводит вуз к каноничному написанию из справочника.

    Если введённое (без учёта регистра, ё/е, пунктуации) точно совпадает с
    названием или алиасом вуза — возвращает каноничное название («мфти» →
    «МФТИ (Московский физико-технический институт)»). Иначе возвращает
    исходный ввод без изменений (свободный ввод сохраняется).
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return stripped
    key = _normalize(stripped)
    return _CANONICAL_BY_KEY.get(key, stripped)


def suggest(query: str, limit: int = 10) -> list[str]:
    """Подсказки вузов по запросу. Пустой запрос → топ популярных."""
    q = _normalize(query)
    if not q:
        # Пустой ввод — показываем самые популярные вузы.
        return [name for name, _rank, _keys in _INDEX[:limit]]

    scored: list[tuple[int, int, str]] = []
    for name, rank, keys in _INDEX:
        pr = _best_match_priority(q, keys)
        if pr is not None:
            scored.append((pr, rank, name))

    # Сортировка: сперва приоритет совпадения, затем популярность.
    scored.sort(key=lambda t: (t[0], t[1]))
    return [name for _pr, _rank, name in scored[:limit]]
