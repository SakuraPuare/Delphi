# Stage 1: build
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ src/

RUN uv sync --no-dev --frozen

# 代码预检查：编译失败则中断 build
RUN uv run --with ruff ruff check src/
RUN python -m compileall -q src/

# Stage 2: runtime
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8888

CMD ["uvicorn", "delphi.api.app:app", "--host", "0.0.0.0", "--port", "8888"]
