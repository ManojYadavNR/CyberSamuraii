import json
import os
import shutil
from pathlib import Path
from typing import Any

from schemas.common import ToolStatus

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PROJECT_ROOT / "config" / "tool_registry.json"


class ToolRegistry:
    """Manages tool installation state and health checks."""

    def __init__(self, registry_path: Path | None = None):
        self.registry_path = registry_path or REGISTRY_PATH
        self._registry: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        if self.registry_path.exists():
            with open(self.registry_path) as f:
                self._registry = json.load(f)
        else:
            self._registry = {}

    def save(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump(self._registry, f, indent=2)

    def get_tool(self, name: str) -> dict[str, Any] | None:
        return self._registry.get(name)

    def list_tools(self) -> list[str]:
        return list(self._registry.keys())

    def is_installed(self, name: str) -> bool:
        tool = self._registry.get(name)
        if not tool:
            return False
        return bool(tool.get("installed", False))

    def set_installed(self, name: str, installed: bool) -> None:
        if name in self._registry:
            self._registry[name]["installed"] = installed
            self.save()

    def get_executable_path(self, name: str) -> Path | None:
        tool = self._registry.get(name)
        if not tool:
            return None
        executable = tool.get("executable")
        if not executable:
            return None
        path = Path(executable)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    def get_tool_path(self, name: str) -> Path | None:
        tool = self._registry.get(name)
        if not tool:
            return None
        tool_path = tool.get("path")
        if not tool_path:
            return None
        path = Path(tool_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    def check_health(self, name: str) -> ToolStatus:
        tool = self._registry.get(name)
        if not tool:
            return ToolStatus.NOT_INSTALLED

        if tool.get("requires_api_key"):
            api_key_env = f"{name.upper()}_API_KEY"
            if not os.environ.get(api_key_env) and not os.environ.get("SHODAN_API_KEY"):
                return ToolStatus.MISSING_API_KEY

        if not tool.get("installed", False):
            return ToolStatus.NOT_INSTALLED

        if tool.get("builtin"):
            return ToolStatus.HEALTHY

        executable = tool.get("executable")
        if executable:
            exec_path = Path(executable)
            if not exec_path.is_absolute():
                exec_path = PROJECT_ROOT / exec_path
            if exec_path.suffix == ".py" and exec_path.exists():
                return ToolStatus.HEALTHY
            if shutil.which(str(executable)) or exec_path.exists():
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY

        tool_path = tool.get("path")
        if tool_path:
            path = Path(tool_path)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if path.exists():
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY

        return ToolStatus.UNHEALTHY

    def check_all_health(self) -> dict[str, ToolStatus]:
        return {name: self.check_health(name) for name in self._registry}


registry = ToolRegistry()
