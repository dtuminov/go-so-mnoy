FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic/ alembic/
COPY bot/ bot/
COPY admin_bot/ admin_bot/

# Default: main bot. Override in docker-compose per service.
CMD ["python", "-m", "bot"]
