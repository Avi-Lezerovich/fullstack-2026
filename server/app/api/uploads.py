"""Image uploads.

Accepting a file from the internet is the most dangerous thing this
application does, so every decision here is a refusal by default:

* **The client's filename is never used.** It is attacker-controlled and is
  the source of every path-traversal bug in every upload endpoint ever
  written. The stored name is 32 hex characters we generate, plus an extension
  we choose from the format we detected.
* **The declared Content-Type is never trusted either.** `image/png` in a
  multipart header is just a string the client typed. The format is decided by
  reading the first bytes of the file, and anything we do not recognise is
  rejected - which is what stops an HTML or SVG payload being stored and later
  served back on our own origin.
* **Size is capped three times**: nginx refuses an oversized body before it
  reaches Python, Flask's MAX_CONTENT_LENGTH refuses it before this view runs,
  and the view measures what actually arrived. The first two are defence, the
  third is the one that produces a Hebrew error message.
* **Serving is by exact name match.** The download route accepts nothing but
  the 32-hex-plus-extension shape it issued, so there is no input from which a
  traversal could be constructed at all.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from .. import security
from ..config import get_settings
from ..errors import fail

bp = Blueprint("uploads", __name__)

# The formats we are willing to store, keyed by the magic bytes that identify
# them. SVG is deliberately absent: it is a document, it can carry script, and
# serving one from our own origin would be a stored-XSS primitive.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)

_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

# Exactly what _store() produces, and nothing else.
_STORED_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|gif|webp)$")


def _detect(head: bytes) -> str | None:
    """The image format these bytes actually are, or None."""
    for signature, extension in _SIGNATURES:
        if head.startswith(signature):
            return extension
    # WEBP is "RIFF" + 4 size bytes + "WEBP", so it cannot be a prefix match.
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _upload_dir() -> Path:
    directory = Path(get_settings().upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@bp.post("/uploads")
@security.require_auth
def upload_image():
    """Store one image and return the URL to reference it by."""
    settings = get_settings()

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return fail("invalid", "לא נבחר קובץ.")

    data = uploaded.read(settings.upload_max_bytes + 1)
    if not data:
        return fail("invalid", "הקובץ ריק.")
    if len(data) > settings.upload_max_bytes:
        megabytes = settings.upload_max_bytes // (1024 * 1024)
        return fail("invalid", f"הקובץ גדול מדי. המגבלה היא {megabytes} מגה-בייט.")

    extension = _detect(data[:16])
    if extension is None:
        return fail("invalid", "אפשר להעלות תמונות בלבד (JPG, PNG, GIF או WEBP).")

    name = f"{secrets.token_hex(16)}.{extension}"
    (_upload_dir() / name).write_bytes(data)

    return jsonify({"url": f"/api/uploads/{name}", "bytes": len(data)}), 201


@bp.get("/uploads/<name>")
def serve_image(name: str):
    """Serve a stored image.

    Public: these are profile pictures and evidence photos on public filings.
    The name has to match the shape we issue exactly - that is the whole of
    the path-traversal defence, and it is stricter than sanitising would be.
    """
    if not _STORED_NAME.match(name):
        return fail("not_found", "הקובץ המבוקש לא נמצא.")

    path = _upload_dir() / name
    if not path.is_file():
        return fail("not_found", "הקובץ המבוקש לא נמצא.")

    extension = name.rsplit(".", 1)[1]
    response = send_from_directory(
        _upload_dir(),
        name,
        # Explicit, so the browser never sniffs a type of its own choosing.
        mimetype=_CONTENT_TYPES[extension],
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    # The name is content-addressed by randomness: it never refers to
    # different bytes, so it can be cached forever.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
