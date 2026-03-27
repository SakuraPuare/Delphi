# Stage 1: build
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --no-dev --frozen

# Stage 2: runtime
FROM python:3.12-slim-bookworm

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8888

CMD ["uvicorn", "delphi.api.app:app", "--host", "0.0.0.0", "--port", "8888"]
