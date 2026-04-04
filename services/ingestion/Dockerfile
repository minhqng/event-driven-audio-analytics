FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY services/ingestion /app/services/ingestion

RUN sed -i 's/\r$//' /app/services/ingestion/entrypoint.sh \
    && pip install --no-cache-dir ".[ingestion]"

ENTRYPOINT ["sh", "/app/services/ingestion/entrypoint.sh"]
