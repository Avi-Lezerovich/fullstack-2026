# Build context is the repo root (see docker-compose.yml) so we can copy both
# the server package and the database/ schema it reads at startup.
FROM python:3.12-slim

WORKDIR /app

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server/ ./server/
COPY database/ ./database/

WORKDIR /app/server
EXPOSE 5001
# Production WSGI server (run.py's debug server is for local dev only).
# run.py exposes `app = create_app()` at module level, so `run:app` works here.
# --preload imports the app (running init_db once) in the master before forking
# workers; otherwise the workers race to seed the DB and deadlock on first boot.
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "3", "--preload", "run:app"]
