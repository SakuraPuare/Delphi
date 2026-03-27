"""模型管理 API 路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from delphi.api.models import ModelActivateRequest, ModelInfoResponse, ModelRegisterRequest
from delphi.models.manager import ModelInfo

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfoResponse])
async def list_models(request: Request) -> list[ModelInfoResponse]:
    """列出所有已注册模型 + vLLM 当前模型"""
    mgr = request.app.state.model_manager
    registered = mgr.list_models()
    vllm_ids = await mgr.get_vllm_models()

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

    return result


@router.post("/register", response_model=ModelInfoResponse, status_code=201)
async def register_model(body: ModelRegisterRequest, request: Request) -> ModelInfoResponse:
    """注册新模型"""
    mgr = request.app.state.model_manager
    if mgr.get(body.name):
        raise HTTPException(status_code=409, detail=f"模型 '{body.name}' 已存在")

    info = ModelInfo(
        name=body.name,
        model_path=body.model_path,
        model_type=body.model_type,
        base_model=body.base_model,
        description=body.description,
    )
    mgr.register(info)
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
    mgr = request.app.state.model_manager
    if not mgr.unregister(name):
        raise HTTPException(status_code=404, detail=f"模型 '{name}' 不存在")


@router.post("/activate", response_model=ModelInfoResponse)
async def activate_model(body: ModelActivateRequest, request: Request) -> ModelInfoResponse:
    """激活/切换模型"""
    mgr = request.app.state.model_manager
    ok = await mgr.activate(body.name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"模型 '{body.name}' 不存在")

    info = mgr.get(body.name)
    return ModelInfoResponse(
        name=info.name,
        model_path=info.model_path,
        model_type=info.model_type,
        base_model=info.base_model,
        description=info.description,
        active=info.active,
    )
