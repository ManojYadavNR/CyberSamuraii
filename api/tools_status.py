from fastapi import APIRouter

from schemas.common import ToolStatus
from tools.registry import registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/status")
async def get_tools_status() -> dict[str, str]:
    """
    Tool health check endpoint.
    Returns status for each registered tool.
    """
    health = registry.check_all_health()
    return {name: status.value for name, status in health.items()}


@router.get("/status/{tool_name}")
async def get_tool_status(tool_name: str) -> dict[str, str]:
    status = registry.check_health(tool_name)
    if tool_name not in registry.list_tools():
        return {"tool": tool_name, "status": ToolStatus.NOT_INSTALLED.value}
    return {"tool": tool_name, "status": status.value}
