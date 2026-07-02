"""Thread-safe ML runtime for linguistic analysis pipelines."""

from __future__ import annotations

import gc
import logging
import os
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterator, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_init_lock = threading.Lock()
_warmed = False
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="linguistic-ml")
_pipelines: dict[str, Any] = {}
_models: dict[str, Any] = {}
_torch_configured = False
_session_depth = 0

LANG_MODEL = "papluca/xlm-roberta-base-language-detection"
SENTIMENT_MODEL = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
NER_MODEL = "Babelscape/wikineural-multilingual-ner"
TOPIC_MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
TOXICITY_MODEL = "unitary/toxic-bert"
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def linguistic_ml_enabled() -> bool:
    return os.getenv("LINGUISTIC_ML_ENABLED", "true").lower() in ("1", "true", "yes", "on")


def _total_ram_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024**2)
    except OSError:
        pass
    return 16.0


def low_memory_mode() -> bool:
    raw = os.getenv("LINGUISTIC_LOW_MEMORY")
    if raw is not None:
        return raw.lower() in ("1", "true", "yes", "on")
    return _total_ram_gb() < 12.0


def fast_linguistic_mode() -> bool:
    """Skip heaviest models (topics, toxicity, embedding cross-links) for speed."""
    raw = os.getenv("LINGUISTIC_FAST_MODE")
    if raw is not None:
        return raw.lower() in ("1", "true", "yes", "on")
    return low_memory_mode()


def max_ml_artifacts() -> int:
    raw = os.getenv("LINGUISTIC_MAX_ARTIFACTS")
    if raw:
        try:
            return max(3, int(raw))
        except ValueError:
            pass
    return 12 if fast_linguistic_mode() else 40


@contextmanager
def analysis_session() -> Iterator[None]:
    """Keep pipelines loaded for one analysis pass; release once at the end."""
    global _session_depth
    with _init_lock:
        _session_depth += 1
    try:
        yield
    finally:
        with _init_lock:
            _session_depth -= 1
            depth = _session_depth
        if depth == 0 and low_memory_mode():
            release_all_pipelines()


def should_release_after_step() -> bool:
    """Only unload between steps when not inside a single analysis session."""
    return low_memory_mode() and _session_depth == 0


def _configure_torch() -> None:
    global _torch_configured
    if _torch_configured:
        return
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    try:
        import torch

        torch.set_num_threads(1)
        if low_memory_mode():
            torch.set_num_interop_threads(1)
    except Exception:
        pass
    _torch_configured = True


def _device() -> int:
    try:
        import torch

        if os.getenv("LINGUISTIC_USE_GPU", "false").lower() in ("1", "true", "yes", "on"):
            return 0 if torch.cuda.is_available() else -1
    except Exception:
        pass
    return -1


def _model_kwargs(model: str) -> dict[str, Any]:
    """Prefer existing PyTorch weights when safetensors downloads were interrupted."""
    kwargs: dict[str, Any] = {"low_cpu_mem_usage": True}
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    folder = os.path.join(cache, "models--" + model.replace("/", "--"))
    if not os.path.isdir(folder):
        return kwargs
    has_pt = any(name == "pytorch_model.bin" for _root, _dirs, files in os.walk(folder) for name in files)
    has_safe = any(name == "model.safetensors" for _root, _dirs, files in os.walk(folder) for name in files)
    incomplete_safe = any(
        name.endswith(".incomplete")
        for _root, _dirs, files in os.walk(folder)
        for name in files
        if "safetensors" in name or name.startswith("model.")
    )
    if has_pt and (not has_safe or incomplete_safe):
        kwargs["use_safetensors"] = False
    return kwargs


def warmup_linguistic_ml() -> None:
    global _warmed
    with _init_lock:
        if _warmed:
            return
        try:
            _configure_torch()
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except Exception as exc:
            logger.warning("Linguistic ML warmup skipped: %r", exc)
            return
        _warmed = True


def release_pipeline(name: str) -> None:
    with _init_lock:
        _pipelines.pop(name, None)
    gc.collect()


def release_model(name: str) -> None:
    with _init_lock:
        _models.pop(name, None)
    gc.collect()


def release_all_pipelines() -> None:
    with _init_lock:
        _pipelines.clear()
        _models.clear()
    gc.collect()


def run_sync(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    warmup_linguistic_ml()
    with analysis_session():
        future = _executor.submit(func, *args, **kwargs)
        return future.result()


def get_pipeline(name: str, *, task: str, model: str, **kwargs: Any) -> Any:
    if name in _pipelines:
        return _pipelines[name]
    with _init_lock:
        if name in _pipelines:
            return _pipelines[name]
        _configure_torch()
        from transformers import pipeline

        logger.info("Loading linguistic pipeline %s (%s)", name, model)
        _pipelines[name] = pipeline(
            task,
            model=model,
            device=_device(),
            model_kwargs=_model_kwargs(model),
            **kwargs,
        )
        return _pipelines[name]


def get_lang_pipeline() -> Any:
    return get_pipeline("lang", task="text-classification", model=LANG_MODEL, top_k=3)


def get_sentiment_pipeline() -> Any:
    return get_pipeline("sentiment", task="sentiment-analysis", model=SENTIMENT_MODEL)


def get_ner_pipeline() -> Any:
    return get_pipeline(
        "ner",
        task="token-classification",
        model=NER_MODEL,
        aggregation_strategy="simple",
    )


def get_topic_pipeline() -> Any:
    return get_pipeline("topics", task="zero-shot-classification", model=TOPIC_MODEL)


def get_toxicity_pipeline() -> Any:
    return get_pipeline("toxicity", task="text-classification", model=TOXICITY_MODEL, top_k=None)


def get_embedding_model() -> Any:
    if "embed" in _models:
        return _models["embed"]
    with _init_lock:
        if "embed" in _models:
            return _models["embed"]
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s", EMBED_MODEL)
        _models["embed"] = SentenceTransformer(EMBED_MODEL)
        return _models["embed"]


def models_used() -> dict[str, str]:
    return {
        "language": LANG_MODEL,
        "sentiment": SENTIMENT_MODEL,
        "ner": NER_MODEL,
        "topics": TOPIC_MODEL,
        "toxicity": TOXICITY_MODEL,
        "embeddings": EMBED_MODEL,
    }
