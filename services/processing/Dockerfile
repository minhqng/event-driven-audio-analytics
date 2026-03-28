FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY services/processing /app/services/processing

RUN sed -i 's/\r$//' /app/services/processing/entrypoint.sh \
    && pip install --no-cache-dir .

ENTRYPOINT ["sh", "/app/services/processing/entrypoint.sh"]
