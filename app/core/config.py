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

    # Окружение: "dev" (локально по HTTP) или "prod". Влияет на выдачу Swagger,
    # флаг Secure у cookie и строгость проверки секретов.
    environment: str = "dev"

    # Веб-приложение
    webapp_base_url: str = "http://localhost:8000"
    jwt_secret: str = ""
    session_ttl_hours: int = 168

    domain: str = "example.com"

    # Email пользователя, которому при старте выдаётся is_admin (доступ к /admin).
    admin_email: str = ""

    # Отправка почты (SMTP). Timeweb: smtp.timeweb.ru, SSL 465,
    # логин = адрес ящика, пароль = пароль ящика.
    smtp_host: str = "smtp.timeweb.ru"
    smtp_port: int = 465
    smtp_user: str = ""  # логин = полный адрес ящика, напр. noreply@obyasny.ru
    smtp_password: str = ""
    smtp_from: str = ""  # адрес отправителя; если пусто — используется smtp_user
    smtp_use_ssl: bool = True  # True → SSL(465); False → STARTTLS(587)

    @property
    def is_prod(self) -> bool:
        return self.environment.strip().lower() in ("prod", "production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # В проде запрещаем стартовать с пустым/дефолтным секретом подписи сессий:
    # иначе злоумышленник сможет подделать JWT и войти под любым пользователем.
    if settings.is_prod:
        weak = {"", "change_me_super_secret_key"}
        if settings.jwt_secret.strip() in weak or len(settings.jwt_secret) < 32:
            raise RuntimeError(
                "jwt_secret не задан или слишком короткий для прода. "
                "Задайте случайный JWT_SECRET (минимум 32 символа) в .env."
            )
    elif not settings.jwt_secret.strip():
        # Dev-фолбэк: фиксированный секрет, чтобы локально не падать по HTTP.
        settings.jwt_secret = "dev-insecure-secret-change-me-in-prod-0000"
    return settings


settings = get_settings()
