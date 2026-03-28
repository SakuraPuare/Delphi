from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

from delphi.core.config import Settings, settings

router = APIRouter(prefix="/settings", tags=["settings"])

_ENV_FILE = Path(".env")

_SECRET_FIELDS = {"llm_api_key", "embedding_api_key", "api_key"}

_GROUPS: dict[str, list[str]] = {
    "llm": ["vllm_url", "llm_model", "llm_api_key", "llm_no_think"],
    "embedding": ["embedding_url", "embedding_model", "embedding_api_key", "embedding_backend"],
    "reranker": ["reranker_url", "reranker_model", "reranker_enabled", "reranker_top_k", "reranker_score_threshold"],
    "rag": ["chunk_top_k", "query_rewrite_enabled", "retrieve_top_k"],
    "server": ["host", "port", "debug", "api_key"],
    "otel": ["otel_enabled", "otel_endpoint", "otel_service_name"],
}


def _mask(value: str) -> str:
    if not value:
        return ""
    return f"****{value[-4:]}" if len(value) > 4 else "****"


def _build_grouped() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group, fields in _GROUPS.items():
        data: dict[str, Any] = {}
        for f in fields:
            v = getattr(settings, f)
            if f in _SECRET_FIELDS:
                v = _mask(str(v)) if isinstance(v, str) else v
            data[f] = v
        result[group] = data
    return result


def _write_env(updates: dict[str, str]) -> None:
    lines: list[str] = []
    seen: set[str] = set()

    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                env_key = stripped.split("=", 1)[0].strip()
                setting_name = env_key.removeprefix("DELPHI_").lower()
                if setting_name in updates:
                    lines.append(f"{env_key}={updates[setting_name]}")
                    seen.add(setting_name)
                    continue
            lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            lines.append(f"DELPHI_{key.upper()}={value}")

    _ENV_FILE.write_text("\n".join(lines) + "\n")


@router.get("")
async def get_settings() -> dict[str, dict[str, Any]]:
    logger.info("收到获取配置请求")
    result = _build_grouped()
    logger.debug("返回配置分组: {}", list(result.keys()))
    return result


@router.put("")
async def update_settings(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    logger.info("收到更新配置请求, keys={}", list(body.keys()))
    known = set(Settings.model_fields.keys())
    env_updates: dict[str, str] = {}

    for key, value in body.items():
        if key not in known:
            logger.warning("未知配置项: {}", key)
            raise HTTPException(status_code=422, detail=f"Unknown setting: {key}")
        setattr(settings, key, value)
        env_updates[key] = str(value).lower() if isinstance(value, bool) else str(value)

    _write_env(env_updates)
    logger.info("配置已更新并写入 .env, 更新项: {}", list(body.keys()))
    return _build_grouped()
