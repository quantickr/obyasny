import secrets
from pathlib import Path

from fastapi import UploadFile

UPLOAD_DIR = Path("/app/uploads")
AVATAR_DIR = UPLOAD_DIR / "avatars"

MAX_SIZE = 5 * 1024 * 1024  # 5 МБ

# Разрешённые типы: сопоставление content_type → расширение.
_ALLOWED = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Сигнатуры (magic bytes) — проверяем реальное содержимое, а не только
# заголовок content_type, который клиент может подделать.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", ".jpg"),  # JPEG
    (b"\x89PNG\r\n\x1a\n", ".png"),  # PNG
]


class UploadError(Exception):
    pass


def _detect_ext(data: bytes, content_type: str | None) -> str:
    for magic, ext in _SIGNATURES:
        if data.startswith(magic):
            return ext
    # WEBP: "RIFF"...."WEBP"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise UploadError("Поддерживаются только изображения JPG, PNG или WEBP")


async def save_avatar(file: UploadFile, user_id: int) -> str:
    """Сохраняет аватар и возвращает публичный URL `/uploads/avatars/<name>`."""
    if file.content_type not in _ALLOWED:
        raise UploadError("Поддерживаются только изображения JPG, PNG или WEBP")

    data = await file.read()
    if len(data) == 0:
        raise UploadError("Файл пустой")
    if len(data) > MAX_SIZE:
        raise UploadError("Файл больше 5 МБ")

    ext = _detect_ext(data, file.content_type)

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{user_id}_{secrets.token_hex(8)}{ext}"
    path = AVATAR_DIR / name
    path.write_bytes(data)

    return f"/uploads/avatars/{name}"
