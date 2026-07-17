from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # База данных
    database_url: str = (
        "postgresql+asyncpg://connectstudents:change_me_in_prod@db:5432/connectstudents"
    )

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Telegram
    bot_token: str = ""
    bot_username: str = "YourBot"

    # Веб-приложение
    webapp_base_url: str = "http://localhost:8000"
    jwt_secret: str = "change_me_super_secret_key"
    session_ttl_hours: int = 168

    domain: str = "example.com"

    # Отправка почты (SMTP). Timeweb: smtp.timeweb.ru, SSL 465,
    # логин = адрес ящика, пароль = пароль ящика.
    smtp_host: str = "smtp.timeweb.ru"
    smtp_port: int = 465
    smtp_user: str = ""  # логин = полный адрес ящика, напр. noreply@obyasny.ru
    smtp_password: str = ""
    smtp_from: str = ""  # адрес отправителя; если пусто — используется smtp_user
    smtp_use_ssl: bool = True  # True → SSL(465); False → STARTTLS(587)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
