"""Фильтр грубой нецензурной брани (RU + EN) с маскировкой на ***.

Задача: ловить грубый мат, включая обходы через leetspeak («bl@t»),
повторы букв («бляяять») и разделители между буквами («б л я т ь»,
«f.u.c.k»), но НЕ трогать мягкие слова («блин», «hell», «damn»).

Как это работает:
1. Строятся ДВЕ нормализованные проекции текста и общая карта индексов:
   - RU-проекция: нижний регистр + leetspeak + транслит латиницы в
     кириллицу (ловит «bl@t», «xyu»), не-буквы отбрасываются.
   - EN-проекция: нижний регистр + leetspeak, латиница как есть
     (ловит «fuck», «f.u.c.k»), не-буквы отбрасываются.
   Обе проекции строятся синхронно и делят одну карту исходных индексов,
   поэтому позиции найденных корней одинаково маппятся в исходный текст.
2. По RU-проекции ищутся русские корни, по EN-проекции — английские.
   Найденные диапазоны переносятся на исходные индексы, и затронутый
   фрагмент исходного текста заменяется на '*'.

Фильтр намеренно узкий: только грубые корни, мягкие слова не включены.
Повторы букв схлопываются на этапе нормализации, разделители внутри
слова отбрасываются — за счёт этого обходы через пробелы/повторы ловятся.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Leetspeak / похожие начертания → каноническая буква (общий этап).
_LEET: dict[str, str] = {
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
    "!": "i",
    "|": "i",
}

# Многосимвольные начертания букв (проверяются ДО посимвольного _LEET).
# «}|{» — распространённый обход буквы «ж» (например «}|{опа»).
_MULTIGLYPH: dict[str, str] = {
    "}|{": "ж",
}
_MULTIGLYPH_MAXLEN = max(len(k) for k in _MULTIGLYPH)

# Транслит латиницы в кириллицу для RU-проекции.
_TRANSLIT_RU: dict[str, str] = {
    "a": "а",
    "b": "б",
    "c": "с",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "x": "х",
    "y": "у",
    "z": "з",
}

# Корни ГРУБОГО мата (кириллица). Мягкие слова НЕ включены сознательно.
# Корень «еб/ёб» ловим ТОЛЬКО с матерными приставками или в начале слова
# с явным матерным окончанием — иначе масса ложных срабатываний («требую»,
# «себе», «небо»). Граница \b работает по краям нормализованной строки.
_RU_ROOTS: list[str] = [
    r"ху[йеяё]",
    # ху[юуи] — только в начале слова: ловит формы «хую», латинские обходы
    # «xyu»→«хуу», «xyi»→«хуи», но не трогает «сухую», «духи», «петухи».
    r"\bху[юуи]",
    r"пизд",
    r"пезд",
    r"бля[дтц]",
    r"\bбля\b",
    r"блуа",  # латинский обход «blyat»/«blyad» → транслит «блуат»/«блуад»
    r"сук[аиеою]",
    r"сучк",
    r"жоп",
    r"анилинг",
    r"кунилинг",  # куннилингус (нн схлопывается в н при нормализации)
    r"минет",
    r"фел[яа]ц",  # фелляция/фелация (лл схлопывается в л при нормализации)
    r"(?:вы|за|на|про|подъ|разъ|съ|у|до|при|от|пере)[еёо]б",
    r"\b[её]б[аеёилмнт]",  # ебать/ебал/ебло/ебёт в начале слова
    r"долбо[её]б",
    r"[её]бан",
    r"мудак",
    r"мудил",
    r"гандон",
    r"гондон",
    r"залуп",
    r"пид[оа]р",
    r"пидр",
    r"дроч",
    r"уёб",
    r"сучар",
    r"сцук",
    r"хер[ануоыть]",
]

# Английские корни (латиница).
_EN_ROOTS: list[str] = [
    r"fuck",
    r"shit",
    r"cunt",
    r"bitch",
    r"asshole",
    r"bastard",
    r"dick",
    r"pussy",
    r"nigger",
    r"motherfuck",
    r"cock",
    r"whore",
    r"slut",
    r"fagot",  # faggot/fagot — «gg» схлопывается в «g» при нормализации
]

_RU_RE = re.compile("|".join(f"(?:{p})" for p in _RU_ROOTS))
_EN_RE = re.compile("|".join(f"(?:{p})" for p in _EN_ROOTS))

_RU_LETTER = re.compile(r"[а-яё]")
_EN_LETTER = re.compile(r"[a-z]")


@dataclass
class _Norm:
    ru: str  # RU-проекция
    en: str  # EN-проекция
    spans: list[list[int]]  # для i-го символа проекции — исходные индексы


def _normalize(text: str) -> _Norm:
    """Строит RU/EN проекции с общей картой исходных индексов.

    Обе проекции синхронны по символам: на каждый значимый символ исходника
    добавляется по одному символу в ru и en (либо оба схлопываются при
    повторе). Разделители/не-буквы отбрасываются, но их индексы привязываются
    к предыдущему символу — чтобы маскировать «б л я т ь» целиком.
    """
    ru_chars: list[str] = []
    en_chars: list[str] = []
    spans: list[list[int]] = []
    prev: str | None = None

    idx = 0
    n = len(text)
    while idx < n:
        # Сначала пробуем многосимвольные начертания («}|{» → «ж»).
        glyph_len = 0
        base = ""
        for length in range(_MULTIGLYPH_MAXLEN, 1, -1):
            chunk = text[idx : idx + length]
            if chunk in _MULTIGLYPH:
                base = _MULTIGLYPH[chunk]
                glyph_len = length
                break
        if glyph_len == 0:
            base = _LEET.get(text[idx].lower(), text[idx].lower())
            glyph_len = 1
        # Индексы всех символов текущего начертания (для маскировки целиком).
        glyph_idxs = list(range(idx, idx + glyph_len))
        idx += glyph_len

        ru_ch = _TRANSLIT_RU.get(base, base if _RU_LETTER.fullmatch(base) else "")
        en_ch = base if _EN_LETTER.fullmatch(base) else ""

        if not ru_ch and not en_ch:
            # разделитель/символ — привязываем к предыдущему значимому символу
            if spans:
                spans[-1].extend(glyph_idxs)
            continue

        key = (ru_ch, en_ch)
        if key == prev:
            # повтор той же буквы — схлопываем
            spans[-1].extend(glyph_idxs)
            continue

        ru_chars.append(ru_ch or "\x00")
        en_chars.append(en_ch or "\x00")
        spans.append(glyph_idxs)
        prev = key

    return _Norm("".join(ru_chars), "".join(en_chars), spans)


def _find_spans(norm: _Norm) -> list[tuple[int, int]]:
    """Диапазоны индексов проекции, покрытые корнями (RU и EN)."""
    hits: list[tuple[int, int]] = []
    for m in _RU_RE.finditer(norm.ru):
        hits.append((m.start(), m.end()))
    for m in _EN_RE.finditer(norm.en):
        hits.append((m.start(), m.end()))
    return hits


def contains_profanity(text: str | None) -> bool:
    if not text:
        return False
    norm = _normalize(text)
    if not norm.spans:
        return False
    return bool(_RU_RE.search(norm.ru) or _EN_RE.search(norm.en))


def censor(text: str | None) -> str | None:
    """Маскирует грубый мат на '*'. Пустой/None возвращает как есть."""
    if not text:
        return text
    norm = _normalize(text)
    if not norm.spans:
        return text

    hits = _find_spans(norm)
    if not hits:
        return text

    chars = list(text)
    for n_start, n_end in hits:
        covered: list[int] = []
        for i in range(n_start, min(n_end, len(norm.spans))):
            covered.extend(norm.spans[i])
        if not covered:
            continue
        lo, hi = min(covered), max(covered)
        for j in range(lo, hi + 1):
            if chars[j].strip():  # пробелы внутри «б л я т ь» не трогаем
                chars[j] = "*"
    return "".join(chars)
