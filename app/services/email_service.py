import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailError(Exception):
    """Не удалось отправить письмо (проблемы SMTP/сети/конфига)."""


async def send_email(to: str, subject: str, body: str) -> None:
    """Отправляет текстовое письмо через SMTP (Timeweb по умолчанию).

    Для SSL(465) используем use_tls=True, для STARTTLS(587) — start_tls=True.
    Бросает EmailError при неудаче, чтобы вызывающий роут показал сообщение.
    """
    if not settings.smtp_user or not settings.smtp_password:
        raise EmailError("SMTP не настроен (SMTP_USER/SMTP_PASSWORD пусты)")

    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_ssl,
            start_tls=not settings.smtp_use_ssl,
        )
    except Exception as e:  # noqa: BLE001 — оборачиваем в доменную ошибку
        logger.warning("Не удалось отправить письмо на %s: %s", to, e)
        raise EmailError("Не удалось отправить письмо") from e


async def send_verification_code(to: str, code: str) -> None:
    """Письмо с 6-значным кодом подтверждения email."""
    subject = "Код подтверждения — Объясни!"
    body = (
        "Здравствуйте!\n\n"
        f"Ваш код подтверждения email: {code}\n\n"
        "Введите его на сайте, чтобы подтвердить почту. "
        "Код действует 15 минут.\n\n"
        "Если вы не запрашивали подтверждение — просто проигнорируйте это письмо.\n\n"
        "— Команда «Объясни!»"
    )
    await send_email(to, subject, body)
