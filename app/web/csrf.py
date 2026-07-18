"""CSRF-защита форм по схеме double-submit cookie.

Токен кладётся в cookie `csrftoken` (доступный из шаблонов/JS), а его копия —
в скрытое поле каждой POST-формы. Middleware на небезопасных методах
(POST/PUT/PATCH/DELETE) сверяет значение из формы со значением из cookie.
Скрытое поле вставляется в HTML автоматически, чтобы не править 60+ форм вручную.
"""

import re
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from app.core.config import settings

CSRF_COOKIE = "csrftoken"
CSRF_FIELD = "csrf_token"
_TOKEN_BYTES = 32

# Методы, не меняющие состояние, — проверять не нужно.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Пути без CSRF-проверки: сюда попадают только те, что не используют
# form-based POST от браузера с cookie-сессией.
#  - /auth/telegram — GET-callback с подписью Telegram (не форма).
#  - /ws/ — WebSocket, аутентифицируется отдельно cookie + проверкой чата.
_EXEMPT_PREFIXES = ("/ws/",)

# Вставляем скрытое поле сразу после открывающего <form ...> у POST-форм.
_FORM_OPEN_RE = re.compile(rb"(<form\b[^>]*\bmethod=[\"']?post[\"']?[^>]*>)", re.IGNORECASE)


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _inject_hidden_inputs(html: bytes, token: str) -> bytes:
    hidden = (
        f'<input type="hidden" name="{CSRF_FIELD}" value="{token}">'
    ).encode()
    return _FORM_OPEN_RE.sub(lambda m: m.group(1) + hidden, html)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cookie_token = request.cookies.get(CSRF_COOKIE)

        # Проверка небезопасных методов.
        method = request.method.upper()
        path = request.url.path
        exempt = any(path.startswith(p) for p in _EXEMPT_PREFIXES)
        if method not in _SAFE_METHODS and not exempt:
            form = await request.form()
            sent = form.get(CSRF_FIELD)
            if (
                not cookie_token
                or not sent
                or not secrets.compare_digest(str(sent), cookie_token)
            ):
                return PlainTextResponse(
                    "CSRF-проверка не пройдена. Обновите страницу и повторите.",
                    status_code=403,
                )

        # Токен для текущего запроса: переиспользуем из cookie либо заводим новый.
        token = cookie_token or generate_token()
        request.state.csrf_token = token

        response: Response = await call_next(request)

        # Автовставка скрытого поля в HTML-ответы.
        ctype = response.headers.get("content-type", "")
        if ctype.startswith("text/html") and hasattr(response, "body_iterator"):
            body = b"".join([chunk async for chunk in response.body_iterator])
            body = _inject_hidden_inputs(body, token)
            headers = dict(response.headers)
            headers.pop("content-length", None)
            response = Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        # Гарантируем наличие cookie с токеном (если её ещё нет).
        if cookie_token is None:
            response.set_cookie(
                CSRF_COOKIE,
                token,
                max_age=settings.session_ttl_hours * 3600,
                httponly=False,  # нужен доступ из JS для fetch-запросов
                samesite="lax",
                secure=settings.is_prod,
            )
        return response
