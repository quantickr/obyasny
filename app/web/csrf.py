"""CSRF-защита форм по схеме double-submit cookie.

Токен кладётся в cookie `csrftoken` (доступный из шаблонов/JS), а его копия —
в скрытое поле каждой POST-формы. На небезопасных методах (POST/PUT/PATCH/DELETE)
значение из формы сверяется со значением из cookie. Скрытое поле вставляется в
HTML автоматически, чтобы не править 60+ форм вручную.

Реализовано как «чистый» ASGI-middleware (а не BaseHTTPMiddleware): последний
вынуждал бы читать тело запроса через `await request.form()`, что исчерпывает
ASGI-поток `receive` и оставляет роут без данных формы (ошибка 422). Здесь тело
буферизуется один раз и передаётся приложению повторно нетронутым.
"""

import re
import secrets
from urllib.parse import parse_qs

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import cookie_parser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

CSRF_COOKIE = "csrftoken"
CSRF_FIELD = "csrf_token"
_TOKEN_BYTES = 32

# Методы, не меняющие состояние, — проверять не нужно.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Пути без CSRF-проверки: сюда попадают только те, что не используют
# form-based POST от браузера с cookie-сессией.
#  - /ws/ — WebSocket, аутентифицируется отдельно cookie + проверкой чата.
_EXEMPT_PREFIXES = ("/ws/",)

# Вставляем скрытое поле сразу после открывающего <form ...> у POST-форм.
_FORM_OPEN_RE = re.compile(
    rb"(<form\b[^>]*\bmethod=[\"']?post[\"']?[^>]*>)", re.IGNORECASE
)


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _inject_hidden_inputs(html: bytes, token: str) -> bytes:
    hidden = (
        f'<input type="hidden" name="{CSRF_FIELD}" value="{token}">'
    ).encode()
    return _FORM_OPEN_RE.sub(lambda m: m.group(1) + hidden, html)


def _extract_field_token(body: bytes, content_type: str) -> str | None:
    """Достаёт csrf_token из тела запроса (urlencoded или multipart),
    не привлекая request.form() и не трогая ASGI-поток."""
    ct = content_type.lower()
    if "application/x-www-form-urlencoded" in ct:
        try:
            parsed = parse_qs(body.decode("latin-1"))
        except Exception:
            return None
        vals = parsed.get(CSRF_FIELD)
        return vals[0] if vals else None
    if "multipart/form-data" in ct:
        # Ищем поле напрямую в сыром multipart без полного парсинга файлов.
        m = re.search(
            rb'name="' + re.escape(CSRF_FIELD.encode())
            + rb'"\r\n\r\n(.*?)\r\n',
            body,
            re.DOTALL,
        )
        if m:
            return m.group(1).decode("latin-1")
    return None


async def _forbidden(send: Send) -> None:
    body = (
        "CSRF-проверка не пройдена. Обновите страницу и повторите."
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class CSRFMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        cookie_token = cookie_parser(headers.get("cookie", "")).get(CSRF_COOKIE)

        method = scope["method"].upper()
        path = scope["path"]
        needs_check = method not in _SAFE_METHODS and not any(
            path.startswith(p) for p in _EXEMPT_PREFIXES
        )

        # Буферизуем тело один раз, чтобы прочитать токен и отдать роуту заново.
        body = b""
        if needs_check:
            more_body = True
            while more_body:
                message = await receive()
                body += message.get("body", b"")
                more_body = message.get("more_body", False)

            sent = _extract_field_token(body, headers.get("content-type", ""))
            if (
                not cookie_token
                or not sent
                or not secrets.compare_digest(str(sent), cookie_token)
            ):
                await _forbidden(send)
                return

        token = cookie_token or generate_token()

        # receive, отдающий буферизованное тело заново (для роута).
        body_sent = False

        async def wrapped_receive() -> Message:
            nonlocal body_sent
            if not needs_check:
                return await receive()
            if not body_sent:
                body_sent = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            return {"type": "http.request", "body": b"", "more_body": False}

        set_cookie_needed = cookie_token is None
        state: dict = {"is_html": False, "start": None, "chunks": []}

        async def wrapped_send(message: Message) -> None:
            mtype = message["type"]
            if mtype == "http.response.start":
                resp_headers = MutableHeaders(raw=list(message["headers"]))
                if set_cookie_needed:
                    secure = "; Secure" if settings.is_prod else ""
                    max_age = settings.session_ttl_hours * 3600
                    resp_headers.append(
                        "set-cookie",
                        f"{CSRF_COOKIE}={token}; Path=/; Max-Age={max_age}; "
                        f"SameSite=Lax{secure}",
                    )
                is_html = resp_headers.get("content-type", "").startswith(
                    "text/html"
                )
                state["is_html"] = is_html
                if is_html:
                    # Тело изменим — content-length пересчитаем в конце.
                    if "content-length" in resp_headers:
                        del resp_headers["content-length"]
                    # start отправим после сборки тела.
                    state["start"] = {
                        "type": "http.response.start",
                        "status": message["status"],
                        "headers": resp_headers.raw,
                    }
                    return
                message["headers"] = resp_headers.raw
                await send(message)
                return

            if mtype == "http.response.body" and state["is_html"]:
                state["chunks"].append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                full = _inject_hidden_inputs(
                    b"".join(state["chunks"]), token
                )
                start = state["start"]
                MutableHeaders(raw=start["headers"])["content-length"] = str(
                    len(full)
                )
                await send(start)
                await send(
                    {
                        "type": "http.response.body",
                        "body": full,
                        "more_body": False,
                    }
                )
                return

            await send(message)

        await self.app(scope, wrapped_receive, wrapped_send)
