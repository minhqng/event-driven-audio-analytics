FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY services/writer /app/services/writer

RUN sed -i 's/\r$//' /app/services/writer/entrypoint.sh \
    && pip install --no-cache-dir .

ENTRYPOINT ["sh", "/app/services/writer/entrypoint.sh"]
