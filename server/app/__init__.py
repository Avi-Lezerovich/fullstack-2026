"""The Flask application factory.

`create_app()` has **no side effects**: it does not touch the database, does
not create a schema and does not seed. The schema is loaded by MySQL's own
entrypoint from database/init.sql, and seeding is a separate one-shot process.

That is a deliberate correction. When the previous version bootstrapped the
database inside the factory, running more than one gunicorn worker meant
several processes racing to create the same tables, which deadlocked and had
to be papered over with `--preload`. Here the factory is pure, so it can be
called freely by tests and by any number of workers.
"""

from __future__ import annotations

from flask import Flask
from flask_cors import CORS

from .api import register_blueprints
from .config import get_settings


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
    app.config["SETTINGS"] = settings

    # Werkzeug aborts the request with 413 once the body passes this, so an
    # oversized upload never reaches a view and never occupies memory. The
    # small headroom is for the multipart envelope around the file itself.
    app.config["MAX_CONTENT_LENGTH"] = settings.upload_max_bytes + 8192

    # supports_credentials because authentication is an httpOnly cookie, not a
    # bearer token - the browser will not attach it otherwise.
    CORS(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": settings.client_origins}},
    )

    register_blueprints(app)
    return app
