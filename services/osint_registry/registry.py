"""Central OSINT tool catalog — plugin discovery + enable/disable + metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from services.osint_registry.tool_metadata import ToolMetadata

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "config" / "osint_catalog.json"
PLUGIN_DIR = ROOT / "services" / "osint_adapters"

# Maps catalog tool_name → orchestrator adapter key (when names differ).
ADAPTER_ALIASES: dict[str, str] = {
    "google_lens": "google_lens",
    "opencv": "opencv_face",
    "opencv_face": "opencv_face",
    "yandex": "yandex_images",
    "yandex_images": "yandex_images",
    "tineye": "tineye",
    "saucenao": "saucenao",
    "facecheck": "facecheck",
    "pimeyes": "pimeyes",
    "gravatar": "gravatar",
    "phoneinfoga": "phoneinfoga",
    "phone_social_intel": "phone_social_intel",
    "public_search": "google_dorking",
    "blackbird": "blackbird",
    "nexfil": "nexfil",
    "gitfive": "gitfive",
    "ghunt": "ghunt",
    "subfinder": "subfinder",
    "amass": "amass",
    "dnsrecon": "dnsrecon",
    "whois": "whois",
}


class OsintRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}
        self._loaded = False

    def reload(self) -> int:
        merged: dict[str, dict[str, Any]] = {}

        if CATALOG_PATH.exists():
            try:
                payload = json.loads(CATALOG_PATH.read_text())
                for entry in payload.get("tools", []):
                    if isinstance(entry, dict) and entry.get("tool_name"):
                        merged[entry["tool_name"]] = entry
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Failed to load OSINT catalog: %s", exc)

        if PLUGIN_DIR.is_dir():
            for path in sorted(PLUGIN_DIR.rglob("*.json")):
                if path.name.startswith("_"):
                    continue
                try:
                    entry = json.loads(path.read_text())
                    if isinstance(entry, dict) and entry.get("tool_name"):
                        name = str(entry["tool_name"])
                        base = merged.get(name, {})
                        merged[name] = {**base, **entry, "plugin_path": str(path.relative_to(ROOT))}
                except (OSError, json.JSONDecodeError) as exc:
                    log.warning("Skipping plugin %s: %s", path, exc)

        self._tools = {}
        for name, raw in merged.items():
            try:
                meta = ToolMetadata(**raw)
                if not meta.adapter_key and not meta.catalog_only:
                    meta.adapter_key = ADAPTER_ALIASES.get(meta.tool_name, meta.tool_name)
                self._tools[meta.tool_name] = meta
            except Exception as exc:
                log.warning("Invalid tool metadata for %s: %s", name, exc)

        self._apply_install_health()
        self._loaded = True
        return len(self._tools)

    def _apply_install_health(self) -> None:
        try:
            from tools.registry import registry as install_registry

            install_registry.reload()
            for name, meta in self._tools.items():
                adapter_key = meta.adapter_key or name
                if meta.catalog_only:
                    continue
                if adapter_key not in install_registry.list_tools():
                    patched = meta.model_copy(update={"catalog_only": True, "enabled": False})
                    self._tools[name] = patched
        except Exception:
            pass

    def list_tools(self) -> list[ToolMetadata]:
        if not self._loaded:
            self.reload()
        return sorted(self._tools.values(), key=lambda t: (t.priority, t.tool_name))

    def get(self, tool_name: str) -> ToolMetadata | None:
        if not self._loaded:
            self.reload()
        return self._tools.get(tool_name)

    def set_enabled(self, tool_name: str, enabled: bool) -> ToolMetadata | None:
        meta = self.get(tool_name)
        if not meta:
            return None
        updated = meta.model_copy(update={"enabled": enabled})
        self._tools[tool_name] = updated
        return updated

    def tools_for_input(
        self,
        input_type: str,
        *,
        feature: str | None = None,
        hop: bool = False,
        profile: str = "fast",
        runnable_only: bool = True,
    ) -> list[ToolMetadata]:
        if not self._loaded:
            self.reload()

        out: list[ToolMetadata] = []
        for meta in self._tools.values():
            if input_type not in meta.supported_inputs:
                continue
            # Route by supported_inputs; feature tags are catalog hints only.
            if hop and not meta.hop_eligible:
                continue
            if not meta.enabled:
                continue
            if runnable_only and not meta.is_runnable():
                continue
            if profile == "fast" and meta.speed == "slow" and input_type != "username":
                continue
            out.append(meta)

        out.sort(key=lambda t: (t.priority, -t.confidence, t.tool_name))
        return out

    def adapter_keys_for_input(self, input_type: str, **kwargs: Any) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()
        for meta in self.tools_for_input(input_type, **kwargs):
            key = meta.adapter_key or meta.tool_name
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
        return keys

    def parallel_groups(self, tools: list[ToolMetadata]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for meta in tools:
            key = meta.adapter_key or meta.tool_name
            groups.setdefault(meta.parallel_group, []).append(key)
        return groups

    def to_api_dict(self) -> dict[str, Any]:
        tools = self.list_tools()
        return {
            "count": len(tools),
            "catalog_path": str(CATALOG_PATH),
            "plugin_dir": str(PLUGIN_DIR),
            "tools": [t.model_dump() for t in tools],
        }


registry = OsintRegistry()
