FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir ".[dataset-exporter]"

ENTRYPOINT ["python", "-m", "event_driven_audio_analytics.dataset_exporter.app"]

