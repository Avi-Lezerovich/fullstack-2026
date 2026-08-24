# Build context is the REPO ROOT, not server/ - the image needs database/
# alongside the code so the schema is available to the container.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./
COPY database/ ./database/

EXPOSE 5001

# Overridden per service in docker-compose.yml: the api runs gunicorn, the
# worker runs run_worker.py, and seed runs app.seed once.
CMD ["gunicorn", "--worker-class", "gthread", "--workers", "2", "--threads", "16", \
     "--timeout", "120", "--graceful-timeout", "10", "--access-logfile", "-", \
     "--bind", "0.0.0.0:5001", "run:app"]
