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
CMD ["python", "run.py"]
