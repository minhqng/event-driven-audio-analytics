FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY services/review /app/services/review

RUN sed -i 's/\r$//' /app/services/review/entrypoint.sh \
    && pip install --no-cache-dir ".[review,writer]"

ENTRYPOINT ["sh", "/app/services/review/entrypoint.sh"]
