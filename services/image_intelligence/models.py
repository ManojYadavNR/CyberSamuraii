"""Cached ML model loaders for image intelligence modules."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def insightface_app():
    import os
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    from services.image_intelligence.runtime import warmup_ml_stack

    warmup_ml_stack()
    from insightface.app import FaceAnalysis

    # InsightFace prints provider/model lines to stdout — keep server logs clean.
    sink = StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
    return app


@lru_cache(maxsize=1)
def yolo_model():
    from services.image_intelligence.runtime import warmup_ml_stack

    warmup_ml_stack()
    from ultralytics import YOLO

    return YOLO("yolov8n.pt")


@lru_cache(maxsize=1)
def grounding_dino():
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    import torch

    model_id = "IDEA-Research/grounding-dino-tiny"
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(
        model_id,
        use_safetensors=False,
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return processor, model, device


@lru_cache(maxsize=1)
def clip_model():
    from transformers import CLIPModel, CLIPProcessor
    import torch

    model_id = "openai/clip-vit-base-patch32"
    processor = CLIPProcessor.from_pretrained(model_id)
    model = CLIPModel.from_pretrained(model_id, use_safetensors=False)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return processor, model, device


@lru_cache(maxsize=1)
def opencv_face_cascade():
    import cv2

    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


@lru_cache(maxsize=1)
def facenet_models():
    import torch
    from facenet_pytorch import InceptionResnetV1, MTCNN

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    mtcnn = MTCNN(keep_all=True, device=device)
    resnet = InceptionResnetV1(pretrained="vggface2").eval().to(device)
    return mtcnn, resnet, device


@lru_cache(maxsize=1)
def easyocr_reader():
    from services.image_intelligence.runtime import warmup_ml_stack

    warmup_ml_stack()
    import easyocr

    return easyocr.Reader(["en"], gpu=False, verbose=False)


@lru_cache(maxsize=1)
def paddle_ocr():
    from services.image_intelligence.runtime import warmup_ml_stack

    warmup_ml_stack()
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    except TypeError:
        return PaddleOCR(use_angle_cls=True, lang="en")


GROUNDING_DINO_LABELS = [
    "logo",
    "uniform",
    "vehicle",
    "building",
    "badge",
    "product",
    "event banner",
    "landmark",
]

CLIP_LABELS = [
    "company logo",
    "police uniform",
    "military uniform",
    "car",
    "truck",
    "building",
    "id badge",
    "product packaging",
    "event banner",
    "famous landmark",
]
