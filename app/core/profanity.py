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
# Скобочные обходы: «]|[», «}|{», «)|(» → «ж» («}|{опа», «]|[опа»);
# «)(», «}{», «][» → «х» («)(уй», «][уй»).
_MULTIGLYPH: dict[str, str] = {
    "]|[": "ж",
    "}|{": "ж",
    ")|(": "ж",
    ")(": "х",
    "}{": "х",
    "][": "х",
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
    # Матерные приставочные формы: приставка (+ опц. твёрдый знак) + «еб/ёб».
    # Гласную «о» в корне НЕ ловим: иначе на склейке слов «могу об…»,
    # «за-об…», «при-об…» ловилось невинное «...об...» (ложные срабатывания).
    r"(?:вы|за|на|про|под|раз|съ|у|до|при|от|пере|об)ъ?[её]б",
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
    r"еблан",
    r"выеб",
    r"наеб",
    r"объеб",
    r"разъеб",
    r"выродок",
    r"шлюх",
    r"проститутк",
    r"хуес",
    r"пиздюк",
    r"уебищ",
    r"пидорас",
]

# Корни УГРОЗ и призывов к насилию (кириллица). Ловим прямые угрозы
# расправы/убийства/причинения вреда. Отдельно от мата, но так же
# блокируют ввод. Формы схлопывают повторы букв при нормализации.
_THREAT_ROOTS: list[str] = [
    r"убью",
    r"убе[йя]",
    r"убива[ють]",
    r"зарежу",
    r"зарежь",
    r"прирежу",
    r"зарез",
    r"застрел",
    r"пристрел",
    r"взорв",
    r"взрыв",
    r"изнасил",
    r"насил",
    r"придушу",
    r"задушу",
    r"удавлю",
    r"повеш",
    r"сдохн",
    r"здохн",
    r"подохн",
    r"сожгу",
    r"спалю тебя",
    r"найду и убью",
    r"расчлен",
    r"отрежу",
    r"выпущу кишки",
    r"кастрир",
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

# Угрозы объединяем с матом в RU-проекцию (та же нормализация ловит обходы).
_RU_RE = re.compile("|".join(f"(?:{p})" for p in _RU_ROOTS + _THREAT_ROOTS))
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


#: Сообщение об ошибке для пользователя при обнаружении мата.
PROFANITY_MESSAGE = (
    "В тексте есть ненормативная лексика. Пожалуйста, замените её."
)


class ProfanityError(Exception):
    """Поднимается, когда ввод содержит грубый мат (для отклонения формы)."""

    def __init__(self, message: str = PROFANITY_MESSAGE):
        super().__init__(message)


def contains_profanity(text: str | None) -> bool:
    if not text:
        return False
    norm = _normalize(text)
    if not norm.spans:
        return False
    return bool(_RU_RE.search(norm.ru) or _EN_RE.search(norm.en))


def ensure_clean(text: str | None) -> str | None:
    """Вернуть text как есть, либо поднять ProfanityError при наличии мата."""
    if contains_profanity(text):
        raise ProfanityError()
    return text


#: Сообщение при отклонении бессмысленного/некорректного названия темы.
GIBBERISH_MESSAGE = (
    "Название выглядит некорректным. Введите осмысленное название темы."
)

_VOWELS = set("аеёиоуыэюяaeiouy")
_LETTER_RE = re.compile(r"[а-яёa-z]", re.IGNORECASE)

# Ряды раскладок клавиатуры (RU ЙЦУКЕН и EN QWERTY) — набор подряд идущих
# по ряду букв («фыва», «qwerty», «asdf») почти всегда мусор.
_KEYBOARD_ROWS: tuple[str, ...] = (
    "йцукенгшщзхъ",
    "фывапролджэ",
    "ячсмитьбю",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
)


def _keyboard_run(word: str) -> bool:
    """Есть ли в слове цепочка ≥4 подряд идущих по ряду клавиатуры букв."""
    for row in _KEYBOARD_ROWS:
        for direction in (row, row[::-1]):
            for start in range(len(direction) - 3):
                if direction[start : start + 4] in word:
                    return True
    return False


class GibberishError(ProfanityError):
    """Поднимается, когда название темы — бессмысленный набор букв.

    Наследуется от ProfanityError, чтобы существующие обработчики
    `except ProfanityError` в роутерах ловили и этот случай, но с
    собственным (более подходящим) текстом сообщения.
    """

    def __init__(self, message: str = GIBBERISH_MESSAGE):
        super().__init__(message)


#: Сообщение при пустом (или состоящем только из пробелов) вводе.
EMPTY_MESSAGE = "Вы вводите пустой ввод."


class EmptyInputError(ProfanityError):
    """Поднимается, когда после очистки от пробелов ввод оказался пустым.

    Наследуется от ProfanityError, чтобы существующие обработчики
    `except ProfanityError` в роутерах ловили и этот случай.
    """

    def __init__(self, message: str = EMPTY_MESSAGE):
        super().__init__(message)


def clean_text(text: str | None) -> str:
    """Убирает пробелы и прочие «пустые» символы по краям и внутри.

    Схлопывает любые последовательности пробельных символов (пробелы,
    табы, переводы строк, неразрывные пробелы и т.п.) в один пробел и
    обрезает края. Пустой/None превращает в пустую строку.
    """
    if not text:
        return ""
    # \s покрывает обычные пробелы; добавляем неразрывный/специальные.
    collapsed = re.sub(r"[\s\u00a0\u2000-\u200b\ufeff]+", " ", text)
    return collapsed.strip()


def ensure_nonempty(text: str | None) -> str:
    """Очищает ввод от пробелов и поднимает EmptyInputError, если пусто."""
    cleaned = clean_text(text)
    if not cleaned:
        raise EmptyInputError()
    return cleaned


def _looks_like_gibberish(text: str) -> bool:
    """Похоже ли название на бессмысленный набор букв.

    Ловит ввод вида «орширириририоирири», «ааааааа», «фыва», «qwerty»:
    смотрим на самое длинное слово и проверяем несколько эвристик —
    отсутствие/избыток гласных, повтор одного слога, мало уникальных букв,
    длинные цепочки согласных. Осмысленные названия (в т.ч. короткие
    «ОС», «БД», «SQL», аббревиатуры) пропускаем.
    """
    words = [w for w in re.split(r"[^а-яёa-z]+", text.lower().replace("ё", "е")) if w]
    if not words:
        return False
    # Оцениваем самое длинное «слово» — там ярче всего виден мусор.
    word = max(words, key=len)
    n = len(word)

    # Набор подряд идущих клавиш («фыва», «qwerty») — мусор при длине ≥4.
    if _keyboard_run(word):
        return True

    # Один символ, повторённый ≥5 раз («ааааа», «ррррр»).
    if n >= 5 and len(set(word)) == 1:
        return True

    # Короткие токены (аббревиатуры, ОС, БД, SQL, C++) дальше не трогаем.
    if n < 6:
        return False

    letters = [c for c in word if _LETTER_RE.fullmatch(c)]
    if len(letters) < 6:
        return False

    vowels = sum(1 for c in letters if c in _VOWELS)
    vowel_ratio = vowels / len(letters)
    # Нормальные слова: гласных обычно 30–60%. Крайности — мусор.
    if vowel_ratio < 0.15 or vowel_ratio > 0.8:
        return True

    # Слишком мало уникальных букв на длинное слово («ааааааа», «абабабаб»).
    uniq = len(set(letters))
    if uniq <= 3 and n >= 7:
        return True
    if uniq / len(letters) < 0.3:
        return True

    # Повторяющийся слог («ририририри», «орирориро»): режем на биграммы и
    # смотрим, не доминирует ли одна пара.
    if n >= 8:
        bigrams = [word[i : i + 2] for i in range(len(word) - 1)]
        if bigrams:
            most = max(bigrams.count(b) for b in set(bigrams))
            if most / len(bigrams) >= 0.4:
                return True

    # Длинная цепочка согласных подряд («фывапролджэ»).
    run = 0
    for c in letters:
        if c in _VOWELS:
            run = 0
        else:
            run += 1
            if run >= 5:
                return True

    return False


def ensure_adequate(text: str | None) -> str:
    """Проверяет пустоту, мат и осмысленность (для названий тем).

    Сначала — очистка от пробелов и проверка на пустоту, затем фильтр
    мата/угроз, затем эвристика на бессмысленный набор букв. Возвращает
    очищенный text либо поднимает соответствующую ошибку.
    """
    cleaned = ensure_nonempty(text)
    ensure_clean(cleaned)
    if _looks_like_gibberish(cleaned):
        raise GibberishError()
    return cleaned


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
