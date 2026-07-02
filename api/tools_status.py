from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user, require_permission
from schemas.common import ToolStatus
from services.osint_registry.router import reload_registry, select_tools
from services.osint_registry.registry import registry
from tools.registry import registry as install_registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolEnableRequest(BaseModel):
    enabled: bool


@router.get("")
async def list_osint_tools(user=Depends(require_permission("view_investigations"))) -> dict:
    """Return full OSINT Framework registry catalog."""
    return registry.to_api_dict()


@router.post("/reload")
async def reload_osint_tools(user=Depends(require_permission("manage_users"))) -> dict:
    """Reload registry catalog + plugins without restarting backend."""
    install_registry.reload()
    payload = reload_registry()
    from orchestrator.config import feature_tools_snapshot
    import orchestrator.config as orch_config

    orch_config.FEATURE_TOOLS = feature_tools_snapshot()
    payload["feature_tools"] = orch_config.FEATURE_TOOLS
    return payload


@router.get("/route/{input_type}")
async def route_tools_for_input(input_type: str, profile: str = "fast", user=Depends(require_permission("view_investigations"))) -> dict:
    plan = select_tools("probe", input_type=input_type, profile=profile)
    return plan.model_dump()


@router.patch("/{tool_name}/enabled")
async def set_tool_enabled(tool_name: str, body: ToolEnableRequest, user=Depends(require_permission("manage_users"))) -> dict:
    updated = registry.set_enabled(tool_name, body.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not in registry")
    return updated.model_dump()


@router.get("/status")
async def get_tools_status(user=Depends(get_current_user)) -> dict[str, str]:
    """
    Tool health check endpoint.
    Returns status for each registered tool.
    """
    health = install_registry.check_all_health()
    return {name: status.value for name, status in health.items()}


@router.get("/status/{tool_name}")
async def get_tool_status(tool_name: str, user=Depends(get_current_user)) -> dict[str, str]:
    status = install_registry.check_health(tool_name)
    if tool_name not in install_registry.list_tools():
        return {"tool": tool_name, "status": ToolStatus.NOT_INSTALLED.value}
    return {"tool": tool_name, "status": status.value}
