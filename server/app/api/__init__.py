"""Blueprint registration.

One blueprint per bounded group of resources, all mounted under /api. Each one
stays thin: parse the request, authorise it, call exactly one service function,
map the result code to a status. Anything that touches SQL belongs in
app/services/.
"""

from __future__ import annotations

from flask import Flask

from . import (
    assist,
    auth,
    cases,
    health,
    messages,
    moderation,
    notifications,
    social,
    trial,
    uploads,
    users,
)

_BLUEPRINTS = [
    health.bp,
    auth.bp,
    users.bp,
    cases.bp,
    social.bp,
    trial.bp,
    moderation.bp,
    notifications.bp,
    messages.bp,
    assist.bp,
    uploads.bp,
]


def register_blueprints(app: Flask) -> None:
    for bp in _BLUEPRINTS:
        app.register_blueprint(bp, url_prefix="/api")
