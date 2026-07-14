from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["bot_username"] = settings.bot_username
templates.env.globals["webapp_base_url"] = settings.webapp_base_url
