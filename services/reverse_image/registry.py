"""Extensible reverse image source registry."""

from __future__ import annotations

from typing import Protocol

from schemas.reverse_image import ReverseImageMatch


class ReverseImageSource(Protocol):
    name: str

    async def search(self, image_path: str, image_url: str | None, *, seed_query: str) -> list[ReverseImageMatch]:
        ...


_SOURCES: dict[str, type] = {}


def register_source(cls: type) -> type:
    _SOURCES[cls.name] = cls
    return cls


def list_sources() -> list[str]:
    return list(_SOURCES.keys())


def build_sources(names: list[str] | None = None) -> list[ReverseImageSource]:
    selected = names or list(_SOURCES.keys())
    out: list[ReverseImageSource] = []
    for name in selected:
        cls = _SOURCES.get(name)
        if cls:
            out.append(cls())
    return out
