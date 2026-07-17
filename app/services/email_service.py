import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailError(Exception):
    """Не удалось отправить письмо (проблемы SMTP/сети/конфига)."""


async def send_email(
    to: str, subject: str, body: str, html_body: str | None = None
) -> None:
    """Отправляет письмо через SMTP (Timeweb по умолчанию).

    Всегда шлёт plain-текст (`body`). Если передан `html_body`, письмо
    становится multipart (text/plain + text/html) — почтовые клиенты
    показывают HTML, а plain остаётся fallback'ом для доставляемости.

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
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_ssl,
            start_tls=not settings.smtp_use_ssl,
            timeout=15,
        )
    except Exception as e:  # noqa: BLE001 — оборачиваем в доменную ошибку
        logger.warning("Не удалось отправить письмо на %s: %s", to, e)
        raise EmailError("Не удалось отправить письмо") from e


def _code_email_html(heading: str, intro: str, code: str, note: str) -> str:
    """Собирает простой inline-styled HTML для письма с кодом.

    Inline-стили — потому что почтовые клиенты (особенно Mail.ru) часто
    вырезают <style> и внешние стили. Дизайн минимальный и «безопасный».
    """
    return (
        '<!DOCTYPE html>'
        '<html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "</head>"
        '<body style="margin:0;padding:0;background:#f1f5f9;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f1f5f9;padding:24px 0;">'
        '<tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:440px;background:#ffffff;border-radius:16px;'
        'border:1px solid #e2e8f0;overflow:hidden;">'
        '<tr><td style="padding:28px 32px;font-family:Arial,Helvetica,sans-serif;'
        'color:#0f172a;">'
        f'<div style="font-size:22px;font-weight:800;margin-bottom:12px;">{heading}</div>'
        f'<p style="font-size:15px;line-height:1.5;color:#334155;margin:0 0 16px;">{intro}</p>'
        f'<div style="font-size:32px;font-weight:800;letter-spacing:8px;'
        'text-align:center;color:#4f46e5;background:#eef2ff;border-radius:12px;'
        f'padding:16px 0;margin:0 0 16px;">{code}</div>'
        f'<p style="font-size:13px;line-height:1.5;color:#64748b;margin:0 0 4px;">{note}</p>'
        '<p style="font-size:13px;line-height:1.5;color:#94a3b8;margin:16px 0 0;">'
        "— Команда «Объясни!»</p>"
        "</td></tr></table></td></tr></table></body></html>"
    )


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
    html_body = _code_email_html(
        heading="Подтверждение email",
        intro="Введите этот код на сайте, чтобы подтвердить почту. "
        "Код действует 15 минут.",
        code=code,
        note="Если вы не запрашивали подтверждение — просто проигнорируйте это письмо.",
    )
    await send_email(to, subject, body, html_body=html_body)


async def send_password_reset_code(to: str, code: str) -> None:
    """Письмо с 6-значным кодом для сброса пароля."""
    subject = "Код для сброса пароля — Объясни!"
    body = (
        "Здравствуйте!\n\n"
        f"Код для сброса пароля: {code}\n\n"
        "Введите его на сайте и задайте новый пароль. "
        "Код действует 15 минут.\n\n"
        "Если вы не запрашивали сброс пароля — просто проигнорируйте это письмо.\n\n"
        "— Команда «Объясни!»"
    )
    html_body = _code_email_html(
        heading="Сброс пароля",
        intro="Введите этот код на сайте и задайте новый пароль. "
        "Код действует 15 минут.",
        code=code,
        note="Если вы не запрашивали сброс пароля — просто проигнорируйте это письмо.",
    )
    await send_email(to, subject, body, html_body=html_body)
