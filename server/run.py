"""Web entry point.

`app` is created at module level so `gunicorn run:app` works. Running this file
directly starts Flask's development server instead.
"""

from __future__ import annotations

from app import create_app
from app.config import get_settings

app = create_app()

if __name__ == "__main__":  # pragma: no cover - dev convenience
    settings = get_settings()
    # threaded=True matters: an SSE stream holds its handler for minutes, and a
    # single-threaded server would stop answering everything else.
    # use_reloader=False keeps one process, so the stream count stays honest.
    app.run(host="0.0.0.0", port=settings.port, threaded=True, use_reloader=False)
