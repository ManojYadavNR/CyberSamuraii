#!/usr/bin/env python3
"""Pre-download image intelligence models one-by-one (run before first investigation).

Usage:
    .venv/bin/python scripts/download_image_models.py --skip yolo
    .venv/bin/python scripts/download_image_models.py --only insightface
    .venv/bin/python scripts/download_image_models.py --only clip grounding_dino

Each step runs in its own process — a crash (e.g. YOLO segfault) won't stop the rest.
Estimated total time (first run): 15–35 minutes (skip yolo saves ~2m).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _step(name: str, fn) -> None:
    print(f"\n{'=' * 60}")
    print(f"STEP: {name}")
    print(f"{'=' * 60}")
    start = time.monotonic()
    fn()
    elapsed = time.monotonic() - start
    print(f"OK   {name} ({elapsed:.1f}s)")


def step_core() -> None:
    from services.image_intelligence.runtime import warmup_ml_stack

    warmup_ml_stack(full=True)


def step_yolo() -> None:
    """Download weights file only — avoids ultralytics segfault on some systems."""
    dest = ROOT / "yolov8n.pt"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"Already present: {dest}")
        return
    url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"
    print(f"Downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)
    print(f"Saved {dest.stat().st_size / 1_000_000:.1f} MB")


def step_insightface() -> None:
    from services.image_intelligence.models import insightface_app

    insightface_app()


def step_clip() -> None:
    from huggingface_hub import snapshot_download

    path = snapshot_download("openai/clip-vit-base-patch32", resume_download=True)
    print(f"Cached at: {path}")
    from services.image_intelligence.models import clip_model

    clip_model()


def step_grounding_dino() -> None:
    from huggingface_hub import snapshot_download

    path = snapshot_download("IDEA-Research/grounding-dino-tiny", resume_download=True)
    print(f"Cached at: {path}")
    from services.image_intelligence.models import grounding_dino

    grounding_dino()


def step_facenet() -> None:
    from services.image_intelligence.models import facenet_models

    facenet_models()


def step_easyocr() -> None:
    from services.image_intelligence.models import easyocr_reader

    easyocr_reader()


def step_paddleocr() -> None:
    from services.image_intelligence.models import paddle_ocr

    paddle_ocr()


def step_deepface() -> None:
    import os
    import tempfile

    from PIL import Image

    from services.image_intelligence.runtime import run_sync

    img = Image.new("RGB", (64, 64), color=(128, 128, 128))
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)

    def _run() -> None:
        from deepface import DeepFace

        DeepFace.represent(path, model_name="Facenet", enforce_detection=False)

    try:
        run_sync(_run)
    finally:
        Path(path).unlink(missing_ok=True)


STEPS: dict[str, tuple[str, callable]] = {
    "core": ("Core libs (numpy, cv2, torch, tensorflow)", step_core),
    "yolo": ("YOLOv8n weights (~6 MB)", step_yolo),
    "insightface": ("InsightFace buffalo_l (~275 MB)", step_insightface),
    "clip": ("CLIP vit-base-patch32 (~350 MB)", step_clip),
    "grounding_dino": ("Grounding DINO tiny (~700 MB)", step_grounding_dino),
    "facenet": ("FaceNet vggface2 weights (~100 MB)", step_facenet),
    "easyocr": ("EasyOCR English models (~100 MB)", step_easyocr),
    "paddleocr": ("PaddleOCR English models (~100 MB)", step_paddleocr),
    "deepface": ("DeepFace + TensorFlow Facenet", step_deepface),
}

ESTIMATES = {
    "core": "10–30s",
    "yolo": "30s–2m",
    "insightface": "2–6m",
    "clip": "2–5m",
    "grounding_dino": "3–8m",
    "facenet": "1–3m",
    "easyocr": "1–3m",
    "paddleocr": "2–5m",
    "deepface": "1–4m",
}

CACHE_HINTS = {
    "insightface": "~/.insightface/models/buffalo_l/",
    "clip": "~/.cache/huggingface/hub/",
    "grounding_dino": "~/.cache/huggingface/hub/",
    "facenet": "torch hub cache",
    "easyocr": "~/.EasyOCR/",
    "paddleocr": "~/.paddleocr/",
    "deepface": "~/.deepface/weights/",
    "yolo": "hackathon/yolov8n.pt",
}


def _run_one_in_subprocess(key: str) -> int:
    """Run a single step in a child process so segfaults don't kill the parent."""
    cmd = [sys.executable, str(Path(__file__).resolve()), "--run-one", key]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def _dispatch_run_one(key: str) -> None:
    label, fn = STEPS[key]
    _step(label, fn)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-download image ML models sequentially")
    parser.add_argument("--only", nargs="+", choices=list(STEPS), help="Download only these steps")
    parser.add_argument("--skip", nargs="+", choices=list(STEPS), help="Skip these steps")
    parser.add_argument("--run-one", choices=list(STEPS), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.run_one:
        try:
            _dispatch_run_one(args.run_one)
        except Exception as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        return 0

    skip = set(args.skip or [])
    if args.only:
        selected = [k for k in args.only if k not in skip]
    else:
        selected = [k for k in STEPS if k not in skip]

    print("Image model pre-download (each step in its own process)")
    print("Core is already done on your machine — you can skip it with --skip core")
    print()
    for key in selected:
        label, _ = STEPS[key]
        hint = CACHE_HINTS.get(key, "")
        extra = f" -> {hint}" if hint else ""
        print(f"  • {key}: {label} — est. {ESTIMATES.get(key, '?')}{extra}")

    total_start = time.monotonic()
    ok: list[str] = []
    failed: list[str] = []

    for key in selected:
        label, _ = STEPS[key]
        print(f"\n>>> Starting {key}...")
        code = _run_one_in_subprocess(key)
        if code == 0:
            ok.append(key)
        else:
            failed.append(key)
            print(f"FAIL {label} (exit code {code})", file=sys.stderr)

    total = time.monotonic() - total_start
    print(f"\n{'=' * 60}")
    print(f"Succeeded ({len(ok)}): {', '.join(ok) or 'none'}")
    if failed:
        print(f"Failed    ({len(failed)}): {', '.join(failed)}")
        print("Re-run failed steps individually, e.g.:")
        for key in failed:
            print(f"  .venv/bin/python scripts/download_image_models.py --only {key}")
    print(f"Total time: {total / 60:.1f} minutes")
    if not failed:
        print("ALL MODELS READY — start backend and upload an image.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
