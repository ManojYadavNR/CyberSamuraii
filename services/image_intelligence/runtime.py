"""Thread-safe ML runtime — prevents numpy/cv2/tensorflow import races."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

_ml_init_lock = threading.Lock()
_warmed_up = False
_ml_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-ml")


def warmup_ml_stack(*, full: bool = False) -> None:
    """Import core ML libs once. Use full=True to also preload torch/tensorflow."""
    global _warmed_up
    with _ml_init_lock:
        if _warmed_up:
            return
        import logging

        logging.getLogger("insightface").setLevel(logging.WARNING)
        logging.getLogger("onnxruntime").setLevel(logging.WARNING)
        import numpy  # noqa: F401
        import numpy.typing  # noqa: F401
        import cv2  # noqa: F401
        from PIL import Image  # noqa: F401
        if full:
            try:
                import scipy  # noqa: F401
            except Exception:
                pass
            try:
                import onnxruntime  # noqa: F401
            except Exception:
                pass
            try:
                import torch  # noqa: F401
            except Exception:
                pass
            try:
                import tensorflow  # noqa: F401
            except Exception:
                pass
        _warmed_up = True


def run_sync(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run a CPU-bound ML callable on the dedicated single-worker executor."""
    warmup_ml_stack()

    def _invoke() -> T:
        return func(*args, **kwargs)

    future = _ml_executor.submit(_invoke)
    return future.result()


async def run_in_ml_thread(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Async wrapper that keeps all heavy ML work off the event loop."""
    warmup_ml_stack()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_ml_executor, lambda: func(*args, **kwargs))
