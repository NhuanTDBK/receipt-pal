FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libclang-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache .

COPY . .

ENV PYTHONPATH=/app

FROM base AS production

CMD ["python", "scripts/run_bot.py"]
