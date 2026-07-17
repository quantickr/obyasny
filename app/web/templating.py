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
