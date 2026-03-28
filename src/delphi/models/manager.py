"""模型管理：注册、切换、LoRA adapter 管理"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from loguru import logger

from delphi.core.config import settings

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
            logger.info("模型注册表已加载, 共 {} 个模型, 路径={}", len(self._models), REGISTRY_FILE)
        else:
            logger.debug("模型注册表文件不存在, 初始化为空: {}", REGISTRY_FILE)

    def _save_registry(self) -> None:
        """保存模型注册表到 JSON 文件"""
        data = [asdict(m) for m in self._models.values()]
        REGISTRY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.debug("模型注册表已保存, 共 {} 个模型", len(data))

    def register(self, info: ModelInfo) -> None:
        """注册一个新模型"""
        self._models[info.name] = info
        self._save_registry()
        logger.info("模型已注册: name={}, path={}, type={}", info.name, info.model_path, info.model_type)

    def unregister(self, name: str) -> bool:
        """注销模型"""
        if name in self._models:
            del self._models[name]
            self._save_registry()
            logger.info("模型已注销: {}", name)
            return True
        logger.warning("注销失败, 模型不存在: {}", name)
        return False

    def list_models(self) -> list[ModelInfo]:
        """列出所有已注册模型"""
        logger.debug("列出所有模型, 共 {} 个", len(self._models))
        return list(self._models.values())

    def get(self, name: str) -> ModelInfo | None:
        return self._models.get(name)

    async def get_vllm_models(self) -> list[str]:
        """查询 vLLM 当前加载的模型"""
        logger.debug("查询 vLLM 模型列表, url={}", settings.vllm_url)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{settings.vllm_url}/v1/models")
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                logger.info("vLLM 模型查询成功, 共 {} 个模型: {}", len(models), models)
                return models
        except Exception as e:
            logger.warning("vLLM 模型查询失败: {}", e)
            return []

    async def activate(self, name: str) -> bool:
        """激活指定模型（更新 settings 中的 llm_model）"""
        info = self._models.get(name)
        if not info:
            logger.warning("模型激活失败, 模型不存在: {}", name)
            return False
        # 更新运行时配置
        old_model = settings.llm_model
        settings.llm_model = info.model_path
        # 标记活跃状态
        for m in self._models.values():
            m.active = False
        info.active = True
        self._save_registry()
        logger.info("模型已激活: {} -> {}, 旧模型={}", name, info.model_path, old_model)
        return True
