"""模型管理 API 路由"""

from __future__ import annotations

from loguru import logger
from fastapi import APIRouter, HTTPException, Request

from delphi.api.models import ModelActivateRequest, ModelInfoResponse, ModelRegisterRequest
from delphi.models.manager import ModelInfo

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfoResponse])
async def list_models(request: Request) -> list[ModelInfoResponse]:
    """列出所有已注册模型 + vLLM 当前模型"""
    logger.info("收到列出模型请求")
    mgr = request.app.state.model_manager
    registered = mgr.list_models()
    vllm_ids = await mgr.get_vllm_models()
    logger.debug("已注册模型数={}, vLLM 模型数={}", len(registered), len(vllm_ids))

    result = [
        ModelInfoResponse(
            name=m.name,
            model_path=m.model_path,
            model_type=m.model_type,
            base_model=m.base_model,
            description=m.description,
            active=m.active,
        )
        for m in registered
    ]

    # 将 vLLM 中已加载但未注册的模型也列出
    registered_paths = {m.model_path for m in registered}
    for vid in vllm_ids:
        if vid not in registered_paths:
            result.append(ModelInfoResponse(name=vid, model_path=vid))

    logger.debug("返回模型列表, 总数={}", len(result))
    return result


@router.post("/register", response_model=ModelInfoResponse, status_code=201)
async def register_model(body: ModelRegisterRequest, request: Request) -> ModelInfoResponse:
    """注册新模型"""
    logger.info("收到注册模型请求, name={}, model_path={}, model_type={}", body.name, body.model_path, body.model_type)
    mgr = request.app.state.model_manager
    if mgr.get(body.name):
        logger.warning("模型已存在, name={}", body.name)
        raise HTTPException(status_code=409, detail=f"模型 '{body.name}' 已存在")

    info = ModelInfo(
        name=body.name,
        model_path=body.model_path,
        model_type=body.model_type,
        base_model=body.base_model,
        description=body.description,
    )
    mgr.register(info)
    logger.info("模型注册成功, name={}", body.name)
    return ModelInfoResponse(
        name=info.name,
        model_path=info.model_path,
        model_type=info.model_type,
        base_model=info.base_model,
        description=info.description,
        active=info.active,
    )


@router.delete("/{name}", status_code=204)
async def unregister_model(name: str, request: Request) -> None:
    """注销模型"""
    logger.info("收到注销模型请求, name={}", name)
    mgr = request.app.state.model_manager
    if not mgr.unregister(name):
        logger.warning("注销失败: 模型不存在, name={}", name)
        raise HTTPException(status_code=404, detail=f"模型 '{name}' 不存在")
    logger.info("模型注销成功, name={}", name)


@router.post("/activate", response_model=ModelInfoResponse)
async def activate_model(body: ModelActivateRequest, request: Request) -> ModelInfoResponse:
    """激活/切换模型"""
    logger.info("收到激活模型请求, name={}", body.name)
    mgr = request.app.state.model_manager
    ok = await mgr.activate(body.name)
    if not ok:
        logger.warning("激活失败: 模型不存在, name={}", body.name)
        raise HTTPException(status_code=404, detail=f"模型 '{body.name}' 不存在")

    info = mgr.get(body.name)
    logger.info("模型激活成功, name={}", body.name)
    return ModelInfoResponse(
        name=info.name,
        model_path=info.model_path,
        model_type=info.model_type,
        base_model=info.base_model,
        description=info.description,
        active=info.active,
    )
