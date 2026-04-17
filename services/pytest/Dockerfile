FROM python:3.12-slim

ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_CPU_VERSION=2.11.0+cpu
ARG TORCHAUDIO_CPU_VERSION=2.11.0+cpu

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY references /app/references

RUN pip install --no-cache-dir \
      --index-url "${PYTORCH_CPU_INDEX_URL}" \
      "torch==${TORCH_CPU_VERSION}" \
      "torchaudio==${TORCHAUDIO_CPU_VERSION}" \
    && pip install --no-cache-dir ".[dev,ingestion,processing,review,writer]"

COPY infra /app/infra
COPY schemas /app/schemas
COPY tests /app/tests

ENTRYPOINT ["python", "-m", "pytest"]
