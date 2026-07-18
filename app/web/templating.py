from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.profanity import censor

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["bot_username"] = settings.bot_username
templates.env.globals["webapp_base_url"] = settings.webapp_base_url


def _censor_filter(value):
    """Маскирует мат при выводе (defence-in-depth). None/пустое — как есть."""
    if not value:
        return value
    return censor(str(value))


# Фильтр {{ text | censor }} для вывода пользовательского контента.
templates.env.filters["censor"] = _censor_filter


def _rating_style(rating) -> str:
    """Inline-style фона/текста бейджа рейтинга: −10 красный … +50 зелёный.
    Плавная интерполяция оттенка HSL (0°→120°) с клампом за границами."""
    try:
        r = int(rating)
    except (TypeError, ValueError):
        r = 0
    lo, hi = -10, 50
    t = (r - lo) / (hi - lo)
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    hue = 120 * t  # 0 = красный, 120 = зелёный
    return (
        f"background-color:hsl({hue:.0f},70%,90%);"
        f"color:hsl({hue:.0f},75%,28%)"
    )


# Фильтр {{ rating | rating_style }} — цвет бейджа рейтинга.
templates.env.filters["rating_style"] = _rating_style
