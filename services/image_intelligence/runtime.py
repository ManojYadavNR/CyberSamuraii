"""Thread-safe ML runtime — prevents numpy/cv2/tensorflow import races."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

_ml_init_lock = threading.Lock()
_executor_lock = threading.Lock()
_warmed_up = False
_ml_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-ml")

# Default per-call ML budget — prevents one hung model load from blocking forever.
_DEFAULT_ML_TIMEOUT = float(os.getenv("IMAGE_ML_CALL_TIMEOUT", "75"))

_NOISY_LOGGERS = (
    "insightface",
    "onnxruntime",
    "ultralytics",
    "torch",
    "torchvision",
    "tensorflow",
    "tf",
    "keras",
    "deepface",
    "facenet_pytorch",
    "easyocr",
    "paddle",
    "paddleocr",
    "ppocr",
    "ppocr.utils",
    "transformers",
    "httpx",
    "httpcore",
    "urllib3",
    "PIL",
    "matplotlib",
    "numba",
    "filelock",
    "huggingface_hub",
)


def _quiet_ml_loggers() -> None:
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)
    # Root third-party chatter during model download
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")
    os.environ.setdefault("GLOG_minloglevel", "3")
    os.environ.setdefault("FLAGS_minloglevel", "3")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("YOLO_VERBOSE", "False")
    try:
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
    except Exception:
        pass


def _reset_ml_executor() -> None:
    """Abandon a stuck ML worker so later tools can run."""
    global _ml_executor
    with _executor_lock:
        old = _ml_executor
        _ml_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-ml")
        try:
            old.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def warmup_ml_stack(*, full: bool = False) -> None:
    """Import core ML libs once. Use full=True to also preload torch/tensorflow."""
    global _warmed_up
    with _ml_init_lock:
        if _warmed_up and not full:
            return
        _quiet_ml_loggers()
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


def run_sync(
    func: Callable[..., T],
    /,
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Run a CPU-bound ML callable on the dedicated single-worker executor."""
    warmup_ml_stack()
    budget = _DEFAULT_ML_TIMEOUT if timeout is None else timeout

    def _invoke() -> T:
        return func(*args, **kwargs)

    with _executor_lock:
        executor = _ml_executor
    future = executor.submit(_invoke)
    try:
        if budget and budget > 0:
            return future.result(timeout=budget)
        return future.result()
    except FuturesTimeoutError as exc:
        _reset_ml_executor()
        raise TimeoutError(f"ML call timed out after {budget}s") from exc


async def run_in_ml_thread(
    func: Callable[..., T],
    /,
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Async wrapper that keeps all heavy ML work off the event loop."""
    warmup_ml_stack()
    loop = asyncio.get_running_loop()
    budget = _DEFAULT_ML_TIMEOUT if timeout is None else timeout

    def _call() -> T:
        return run_sync(func, *args, timeout=budget, **kwargs)

    return await loop.run_in_executor(None, _call)
