#!/usr/bin/env python3
"""Pre-download Hugging Face models for linguistic ML (safe for low-RAM machines)."""

from __future__ import annotations

import argparse
import gc
import os
import sys
from pathlib import Path

# Allow `from services...` when run as a script.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Core weights + tokenizers only — skip ONNX/OpenVINO exports (saves GB and time).
_TRANSFORMER_PATTERNS = [
    "*.json",
    "*.txt",
    "*.model",
    "tokenizer*",
    "vocab.*",
    "merges.txt",
    "model.safetensors",
    "pytorch_model.bin",
    "spiece.model",
    "sentencepiece.bpe.model",
    "README.md",
]
_EMBED_PATTERNS = [
    *_TRANSFORMER_PATTERNS,
    "1_Pooling/*",
    "2_Dense/*",
    "modules.json",
    "sentence_bert_config.json",
]


def _clean_incomplete_cache() -> int:
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    removed = 0
    for path in cache.rglob("*.incomplete"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _snapshot_download(repo_id: str, *, allow_patterns: list[str]) -> None:
    from huggingface_hub import snapshot_download

    print(f"  → {repo_id}")
    snapshot_download(repo_id, allow_patterns=allow_patterns)


def _weight_ready(repo_id: str) -> bool:
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    folder = cache / ("models--" + repo_id.replace("/", "--"))
    if not folder.is_dir():
        return False
    min_bytes = 100 * 1024 * 1024  # 100 MB — real model weights, not configs
    for name in ("model.safetensors", "pytorch_model.bin"):
        for path in folder.rglob(name):
            if path.is_symlink() or path.is_file():
                try:
                    if path.stat().st_size >= min_bytes:
                        return True
                except OSError:
                    continue
    return False


def _verify_repos(repos: list[tuple[str, list[str]]]) -> bool:
    ok = True
    print("\nVerifying cached model weights (disk only, no RAM load)...")
    for repo, _patterns in repos:
        if _weight_ready(repo):
            print(f"  ✓ {repo}")
        else:
            print(f"  ✗ {repo} — weights missing or incomplete")
            ok = False
    return ok


def _warmup_one(label: str, loader) -> None:
    print(f"  warming {label}...", flush=True)
    loader()
    from services.linguistic.runtime import release_all_pipelines

    release_all_pipelines()
    gc.collect()
    print(f"  ✓ {label}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download linguistic ML models safely.")
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Load each model once to verify (uses RAM; skip on 7 GB machines).",
    )
    args = parser.parse_args()

    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    from services.linguistic.runtime import (
        EMBED_MODEL,
        LANG_MODEL,
        NER_MODEL,
        SENTIMENT_MODEL,
        TOPIC_MODEL,
        TOXICITY_MODEL,
    )

    repos: list[tuple[str, list[str]]] = [
        (LANG_MODEL, _TRANSFORMER_PATTERNS),
        (SENTIMENT_MODEL, _TRANSFORMER_PATTERNS),
        (NER_MODEL, _TRANSFORMER_PATTERNS),
        (TOPIC_MODEL, _TRANSFORMER_PATTERNS),
        (TOXICITY_MODEL, _TRANSFORMER_PATTERNS),
        (EMBED_MODEL, _EMBED_PATTERNS),
    ]

    removed = _clean_incomplete_cache()
    if removed:
        print(f"Removed {removed} stale .incomplete download(s).")

    print("Downloading linguistic model weights (core files only)...")
    for repo, patterns in repos:
        if _weight_ready(repo):
            print(f"  ✓ cached {repo}")
            continue
        try:
            _snapshot_download(repo, allow_patterns=patterns)
        except Exception as exc:
            print(f"  ! failed {repo}: {exc}")
            return 1

    if not _verify_repos(repos):
        return 1

    if args.warmup:
        print("\nWarming pipelines one at a time (low-memory mode)...")
        from services.linguistic.runtime import (
            get_embedding_model,
            get_lang_pipeline,
            get_ner_pipeline,
            get_sentiment_pipeline,
            get_topic_pipeline,
            get_toxicity_pipeline,
            release_all_pipelines,
            warmup_linguistic_ml,
        )

        warmup_linguistic_ml()
        steps = [
            ("language", get_lang_pipeline),
            ("sentiment", get_sentiment_pipeline),
            ("ner", get_ner_pipeline),
            ("topics", get_topic_pipeline),
            ("toxicity", get_toxicity_pipeline),
            ("embeddings", get_embedding_model),
        ]
        for label, loader in steps:
            try:
                _warmup_one(label, loader)
            except Exception as exc:
                print(f"  ! warmup failed for {label}: {exc}")
                release_all_pipelines()
                return 1

    print("\nLinguistic ML models ready.")
    print("  Downloads: complete (verified on disk).")
    if args.warmup:
        print("  Warmup: all pipelines loaded successfully.")
    else:
        print("  Warmup: skipped (models load on first investigation; one at a time).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
