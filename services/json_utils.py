"""Convert investigation payloads to JSON-safe Python types."""

from __future__ import annotations

from typing import Any


def is_empty_value(value: Any) -> bool:
    """Safe emptiness check — never use truthiness on numpy/torch arrays."""
    if value is None:
        return True
    mod = getattr(type(value), "__module__", "")
    if mod.startswith("numpy"):
        return value.size == 0
    if mod.startswith("torch"):
        try:
            return value.numel() == 0
        except Exception:
            return False
    if value == "" or value == {} or value == []:
        return True
    if isinstance(value, (list, tuple, set, dict, str, bytes)):
        return len(value) == 0
    return False


def embedding_nonempty(emb: Any) -> bool:
    """Safe non-empty check for face embeddings (list or numpy array)."""
    if emb is None:
        return False
    mod = getattr(type(emb), "__module__", "")
    if mod.startswith("numpy"):
        return emb.size > 0
    if isinstance(emb, (list, tuple)):
        return len(emb) > 0
    return bool(emb)


def sequence_nonempty(value: Any) -> bool:
    """Safe non-empty check for lists, tuples, numpy arrays, and torch tensors."""
    if value is None:
        return False
    mod = getattr(type(value), "__module__", "")
    if mod.startswith("numpy"):
        return value.size > 0
    if mod.startswith("torch"):
        try:
            return value.numel() > 0
        except Exception:
            return True
    if isinstance(value, (list, tuple, set, dict, str, bytes)):
        return len(value) > 0
    return bool(value)


def normalize_embedding(emb: Any) -> list[float] | None:
    """Convert embedding to a plain list, or None if missing/empty."""
    if not embedding_nonempty(emb):
        return None
    mod = getattr(type(emb), "__module__", "")
    if mod.startswith("numpy"):
        return emb.astype("float32").flatten().tolist()
    return [float(x) for x in emb]


def to_json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float)):
        return obj
    if isinstance(obj, bool):
        return bool(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    mod = getattr(type(obj), "__module__", "")
    if mod.startswith("numpy"):
        if hasattr(obj, "item"):
            try:
                return to_json_safe(obj.item())
            except Exception:
                pass
        if hasattr(obj, "tolist"):
            try:
                return to_json_safe(obj.tolist())
            except Exception:
                pass
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json_safe(v) for v in obj]
    return str(obj)
