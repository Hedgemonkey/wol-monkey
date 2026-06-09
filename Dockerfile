# syntax=docker/dockerfile:1
# WoL-Monkey — single image for API and worker processes.
FROM python:3.12-slim

WORKDIR /app

# etherwake requires CAP_NET_RAW / network_mode:host when used in worker
# iputils-ping is used by StateProbe
RUN apt-get update && apt-get install -y --no-install-recommends \
        etherwake \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        gunicorn \
        "sqlalchemy>=2.0.0" \
        alembic \
        asyncpg \
        psycopg2-binary \
        "pydantic>=2.7.0" \
        "pydantic-settings>=2.3.0" \
        "argon2-cffi>=23.1.0" \
        "itsdangerous>=2.2.0" \
        "python-multipart>=0.0.9" \
        "jinja2>=3.1.0" \
        httpx \
        structlog

# Copy source
COPY app/ ./app/
COPY worker/ ./worker/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Non-root user
RUN useradd -m -u 1000 wol && chown -R wol:wol /app
USER wol

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Default: API server.
# For the worker, override CMD in docker-compose.yml.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", "-w", "2", "--timeout", "120", "app.main:app"]
