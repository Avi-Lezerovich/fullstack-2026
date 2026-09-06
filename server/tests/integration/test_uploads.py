# -*- coding: utf-8 -*-
"""Image uploads - the most dangerous thing this application does.

The module's own docstring lists four refusals, and every one of them is a
class of bug rather than a validation nicety:

* the client's filename is never used - it is attacker-controlled, and it is
  the source of every path-traversal bug in every upload endpoint ever written;
* the declared Content-Type is never trusted - `image/png` in a multipart
  header is a string the client typed, so the format is decided by reading the
  first bytes;
* size is capped three times, and only the third produces a Hebrew message;
* serving is by exact name match against the shape we issue, which is stricter
  than sanitising and leaves nothing from which a traversal could be built.

SVG's absence from the accepted formats is the sharpest of these and the
easiest to undo by accident: it is a document, it can carry script, and serving
one back from our own origin would be a stored-XSS primitive. There is a test
for it below precisely because "add SVG, it's an image" is such a reasonable-
sounding change.

Uploads land in `settings.upload_dir`, redirected to a tmp_path here so the
suite never writes into the repository's own uploads directory.
"""

from __future__ import annotations

import io

import pytest

pytestmark = pytest.mark.integration

# The first bytes each format is identified by. Real files, not plausible ones:
# the point of the check is that these exact prefixes are what is looked at.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF87 = b"GIF87a" + b"\x00" * 64
GIF89 = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<!doctype html><script>alert(1)</script>"


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    """Somewhere disposable, so the suite never writes into server/uploads."""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    return tmp_path / "uploads"


@pytest.fixture
def uploader(client, make_user, signed_in):
    signed_in(make_user("המעלה", "uploader@lolsuit.test"))
    return client


def _send(client, data: bytes, filename: str = "photo.png", field: str = "file"):
    return client.post(
        "/api/uploads",
        data={field: (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


# --- what is accepted -------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "extension"),
    [(PNG, "png"), (JPEG, "jpg"), (GIF87, "gif"), (GIF89, "gif"), (WEBP, "webp")],
    ids=["png", "jpeg", "gif87", "gif89", "webp"],
)
def test_each_accepted_format_is_recognised_by_its_magic_bytes(uploader, data, extension):
    """WEBP is the one that cannot be a prefix match.

    Its signature is "RIFF", four size bytes, then "WEBP" - so a naive
    startswith table would either miss it or accept every RIFF container,
    including audio.
    """
    response = _send(uploader, data)

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["url"].endswith(f".{extension}")
    assert payload["bytes"] == len(data)


def test_the_stored_name_is_ours_and_owes_nothing_to_the_client(uploader, upload_dir):
    """The uploaded filename is attacker-controlled and is simply discarded.

    Not sanitised - discarded. Thirty-two hex characters we generate plus an
    extension we chose from what we detected, so there is no input left from
    which a traversal could be constructed.
    """
    import re

    response = _send(uploader, PNG, filename="../../../../etc/passwd.png")

    assert response.status_code == 201
    name = response.get_json()["url"].rsplit("/", 1)[1]
    assert re.fullmatch(r"[0-9a-f]{32}\.png", name)
    assert "passwd" not in name
    assert (upload_dir / name).is_file()


def test_two_uploads_of_identical_bytes_get_different_names(uploader):
    """The name is random rather than a content hash.

    Which means one person's upload can never be overwritten - or discovered -
    by somebody uploading the same file.
    """
    first = _send(uploader, PNG).get_json()["url"]
    second = _send(uploader, PNG).get_json()["url"]

    assert first != second


# --- what is refused --------------------------------------------------------


def test_an_svg_is_refused_however_it_is_labelled(uploader):
    """SVG is a document that can carry script.

    Served back from our own origin it would be a stored-XSS primitive, so it
    is absent from the signature table on purpose - and the declared
    Content-Type below is ignored, which is what makes the refusal hold.
    """
    response = uploader.post(
        "/api/uploads",
        data={"file": (io.BytesIO(SVG), "drawing.svg", "image/svg+xml")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400


def test_the_declared_content_type_is_never_believed(uploader):
    """`image/png` in a multipart header is a string the client typed.

    The bytes are HTML; the header says PNG; the bytes win.
    """
    response = uploader.post(
        "/api/uploads",
        data={"file": (io.BytesIO(HTML), "innocent.png", "image/png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "תמונות" in response.get_json()["error"]


def test_a_png_extension_on_a_non_image_does_not_save_it(uploader, upload_dir):
    """The extension is decided by the detected format, never by the name.

    A file whose bytes match nothing is refused before anything is written.
    """
    assert _send(uploader, b"just some text", filename="pretend.png").status_code == 400

    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


def test_an_empty_or_absent_file_is_refused_with_its_own_message(uploader):
    """Two different mistakes, two different sentences.

    "You chose nothing" and "the file you chose is empty" are different things
    to fix.
    """
    missing = uploader.post("/api/uploads", data={}, content_type="multipart/form-data")
    unnamed = _send(uploader, PNG, filename="")
    empty = _send(uploader, b"")

    assert missing.status_code == unnamed.status_code == empty.status_code == 400
    assert missing.get_json()["error"] == unnamed.get_json()["error"]
    assert empty.get_json()["error"] != missing.get_json()["error"]


def test_an_oversized_file_is_measured_rather_than_trusted(uploader, monkeypatch):
    """The third of the three caps, and the only one that speaks Hebrew.

    nginx and Flask's MAX_CONTENT_LENGTH refuse a large body before this view
    runs; this one measures what actually arrived and says how big is allowed.
    """
    monkeypatch.setenv("UPLOAD_MAX_BYTES", str(2 * 1024 * 1024))

    response = _send(uploader, PNG + b"\x00" * (2 * 1024 * 1024))

    assert response.status_code == 400
    assert "2" in response.get_json()["error"]


def test_a_body_past_flasks_own_ceiling_never_reaches_the_view(app, uploader):
    """MAX_CONTENT_LENGTH is set from the same setting plus a small headroom
    for the multipart envelope.

    Werkzeug aborts with 413 before any view runs, so an oversized upload never
    occupies memory.
    """
    settings = app.config["SETTINGS"]
    assert app.config["MAX_CONTENT_LENGTH"] == settings.upload_max_bytes + 8192

    response = _send(uploader, PNG + b"\x00" * (settings.upload_max_bytes + 16384))

    assert response.status_code == 413


def test_uploading_needs_a_session(client):
    """Anonymous writes to disk are how an open bucket happens."""
    assert _send(client, PNG).status_code == 401


# --- serving ----------------------------------------------------------------


def test_a_stored_image_is_served_back_with_its_real_type_and_nosniff(uploader):
    """Explicit mimetype plus `nosniff`, so the browser never chooses.

    Content sniffing is what turns "a file we decided is a GIF" back into
    "whatever the browser thinks it looks like".
    """
    url = _send(uploader, PNG).get_json()["url"]

    response = uploader.get(url)

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.get_data() == PNG


def test_images_are_cached_forever_because_a_name_never_changes_meaning(uploader):
    """Content-addressed by randomness rather than by hash, but the property
    that matters is the same: this name will never refer to different bytes."""
    url = _send(uploader, JPEG).get_json()["url"]

    cache_control = uploader.get(url).headers["Cache-Control"]

    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control


def test_stored_images_are_public(client, uploader):
    """Profile pictures and evidence photos on public filings.

    Requiring a session to load them would break every signed-out page.
    """
    url = _send(uploader, PNG).get_json()["url"]

    assert client.get(url).status_code == 200


@pytest.mark.parametrize(
    "name",
    [
        "../../../etc/passwd",
        "..%2f..%2fsecret.png",
        "not-hex-at-all.png",
        "deadbeefdeadbeefdeadbeefdeadbeef.svg",
        "deadbeefdeadbeefdeadbeefdeadbeef.php",
        "DEADBEEFDEADBEEFDEADBEEFDEADBEEF.png",
        "deadbeefdeadbeefdeadbeefdeadbee.png",
    ],
    ids=["traversal", "encoded", "not-hex", "svg-ext", "php-ext", "uppercase", "too-short"],
)
def test_anything_that_is_not_a_name_we_issued_is_a_404(client, name):
    """The whole path-traversal defence, and it is an allow-list.

    Stricter than sanitising: there is no transformation of a hostile name that
    lands inside the accepted shape, so nothing has to be got right twice.
    """
    assert client.get(f"/api/uploads/{name}").status_code == 404


def test_a_well_formed_name_for_a_file_that_is_not_there_is_a_404(client):
    """Same answer as a malformed one, so the endpoint is not a directory
    listing by exhaustion."""
    response = client.get("/api/uploads/" + "a" * 32 + ".png")

    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


def test_an_uploaded_image_can_be_attached_to_a_filing(uploader, db, make_user, signed_in):
    """The end-to-end reason the endpoint exists.

    The URL it returns is what `image_url` holds, so a change to the shape of
    one has to be a change to the other.
    """
    url = _send(uploader, PNG).get_json()["url"]

    response = uploader.post(
        "/api/cases",
        json={
            "title": "תביעה עם ראיה מצולמת",
            "body": "התמונה מדברת בעד עצמה, כפי שאפשר לראות.",
            "defendant_text": "הצלם",
            "image_url": url,
        },
    )

    assert response.status_code == 201
    assert response.get_json()["case"]["image_url"] == url
