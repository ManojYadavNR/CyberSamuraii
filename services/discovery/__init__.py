"""Recursive Intelligence Discovery Engine."""

__all__ = ["RecursiveDiscoveryEngine"]


def __getattr__(name: str):
    if name == "RecursiveDiscoveryEngine":
        from services.discovery.engine import RecursiveDiscoveryEngine
        return RecursiveDiscoveryEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
