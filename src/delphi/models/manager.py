"""模型管理：注册、切换、LoRA adapter 管理"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from delphi.core.config import settings

logger = logging.getLogger(__name__)

MODELS_DIR = Path.home() / ".delphi" / "models"
REGISTRY_FILE = MODELS_DIR / "registry.json"


@dataclass
class ModelInfo:
    name: str  # 用户自定义名称
    model_path: str  # HuggingFace ID 或本地路径
    model_type: str = "base"  # "base" | "lora"
    base_model: str = ""  # LoRA 的基础模型（仅 lora 类型需要）
    description: str = ""
    active: bool = False


class ModelManager:
    """模型注册与管理"""

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """从 JSON 文件加载模型注册表"""
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        if REGISTRY_FILE.exists():
            data = json.loads(REGISTRY_FILE.read_text())
            for item in data:
                info = ModelInfo(**item)
                self._models[info.name] = info

    def _save_registry(self) -> None:
        """保存模型注册表到 JSON 文件"""
        data = [asdict(m) for m in self._models.values()]
        REGISTRY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def register(self, info: ModelInfo) -> None:
        """注册一个新模型"""
        self._models[info.name] = info
        self._save_registry()

    def unregister(self, name: str) -> bool:
        """注销模型"""
        if name in self._models:
            del self._models[name]
            self._save_registry()
            return True
        return False

    def list_models(self) -> list[ModelInfo]:
        """列出所有已注册模型"""
        return list(self._models.values())

    def get(self, name: str) -> ModelInfo | None:
        return self._models.get(name)

    async def get_vllm_models(self) -> list[str]:
        """查询 vLLM 当前加载的模型"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{settings.vllm_url}/v1/models")
                resp.raise_for_status()
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning("Failed to query vLLM models: %s", e)
            return []

    async def activate(self, name: str) -> bool:
        """激活指定模型（更新 settings 中的 llm_model）"""
        info = self._models.get(name)
        if not info:
            return False
        # 更新运行时配置
        settings.llm_model = info.model_path
        # 标记活跃状态
        for m in self._models.values():
            m.active = False
        info.active = True
        self._save_registry()
        return True
