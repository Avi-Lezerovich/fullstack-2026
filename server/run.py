"""Web entry point.

`app` is created at module level so `gunicorn run:app` works. Running this file
directly starts Flask's development server instead.
"""

from __future__ import annotations

import logging

from app import create_app
from app.config import get_settings

# At module level, so it applies under gunicorn too - gunicorn imports this file
# and never runs the __main__ block. Without it the application's own loggers
# fall back to the root logger's WARNING default, and every log.info the code
# writes - "mail delivered to ...", among others - is discarded before it
# reaches the container log, which is the only place anyone can read it.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)

app = create_app()

if __name__ == "__main__":  # pragma: no cover - dev convenience
    settings = get_settings()
    # threaded=True matters: an SSE stream holds its handler for minutes, and a
    # single-threaded server would stop answering everything else.
    # use_reloader=False keeps one process, so the stream count stays honest.
    app.run(host="0.0.0.0", port=settings.port, threaded=True, use_reloader=False)
