"""Parallel image intelligence adapters — full implementations via Image Intelligence Engine."""

from __future__ import annotations

from adapters.base import BaseAdapter
from schemas.common import ToolResult
from services.image_intelligence import tool_runners as runners


class ImageToolAdapter(BaseAdapter):
    """Image tool adapter — delegates to image intelligence analyzers."""

    group: str = "metadata"
    max_retries: int = 0

    def verify_tool(self) -> tuple[bool, str | None]:
        return True, None


class PillowAdapter(ImageToolAdapter):
    name = "pillow"
    group = "metadata"
    default_timeout = 30.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_pillow(query)


class ExifToolAdapter(ImageToolAdapter):
    name = "exiftool"
    group = "metadata"
    default_timeout = 25.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_exiftool(query)


class HachoirAdapter(ImageToolAdapter):
    name = "hachoir"
    group = "metadata"
    default_timeout = 25.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_hachoir(query)


class InsightFaceAdapter(ImageToolAdapter):
    name = "insightface"
    group = "face_analysis"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_insightface(query)


class DeepFaceAdapter(ImageToolAdapter):
    name = "deepface"
    group = "face_analysis"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_deepface(query)


class FaceNetAdapter(ImageToolAdapter):
    name = "facenet"
    group = "face_analysis"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_facenet(query)


class OpenCVFaceAdapter(ImageToolAdapter):
    name = "opencv_face"
    group = "face_analysis"
    default_timeout = 30.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_opencv_face(query)


class GoogleLensAdapter(ImageToolAdapter):
    name = "google_lens"
    group = "reverse_image_search"
    default_timeout = 45.0

    async def _execute(self, query: str) -> ToolResult:
        from services.reverse_image.tool_runners import run_google_lens
        return await run_google_lens(query)


class BingVisualAdapter(ImageToolAdapter):
    name = "bing_visual"
    group = "reverse_image_search"
    default_timeout = 45.0

    async def _execute(self, query: str) -> ToolResult:
        from services.reverse_image.tool_runners import run_bing_visual
        return await run_bing_visual(query)


class YandexImagesAdapter(ImageToolAdapter):
    name = "yandex_images"
    group = "reverse_image_search"
    default_timeout = 45.0

    async def _execute(self, query: str) -> ToolResult:
        from services.reverse_image.tool_runners import run_yandex_images
        return await run_yandex_images(query)


class TinEyeAdapter(ImageToolAdapter):
    name = "tineye"
    group = "reverse_image_search"
    default_timeout = 45.0

    async def _execute(self, query: str) -> ToolResult:
        from services.reverse_image.tool_runners import run_tineye
        return await run_tineye(query)


class TesseractAdapter(ImageToolAdapter):
    name = "tesseract"
    group = "ocr"
    default_timeout = 40.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_tesseract(query)


class EasyOCRAdapter(ImageToolAdapter):
    name = "easyocr"
    group = "ocr"
    default_timeout = 60.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_easyocr(query)


class PaddleOCRAdapter(ImageToolAdapter):
    name = "paddleocr"
    group = "ocr"
    default_timeout = 60.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_paddleocr(query)


class YoloAdapter(ImageToolAdapter):
    name = "yolo"
    group = "object_detection"
    default_timeout = 60.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_yolo(query)


class GroundingDinoAdapter(ImageToolAdapter):
    name = "grounding_dino"
    group = "object_detection"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_grounding_dino(query)


class ClipAdapter(ImageToolAdapter):
    name = "clip"
    group = "object_detection"
    default_timeout = 45.0

    async def _execute(self, query: str) -> ToolResult:
        return await runners.run_clip(query)


IMAGE_ADAPTER_CLASSES: dict[str, type[BaseAdapter]] = {
    "pillow": PillowAdapter,
    "exiftool": ExifToolAdapter,
    "hachoir": HachoirAdapter,
    "insightface": InsightFaceAdapter,
    "deepface": DeepFaceAdapter,
    "facenet": FaceNetAdapter,
    "opencv_face": OpenCVFaceAdapter,
    "google_lens": GoogleLensAdapter,
    "bing_visual": BingVisualAdapter,
    "yandex_images": YandexImagesAdapter,
    "tineye": TinEyeAdapter,
    "tesseract": TesseractAdapter,
    "easyocr": EasyOCRAdapter,
    "paddleocr": PaddleOCRAdapter,
    "yolo": YoloAdapter,
    "grounding_dino": GroundingDinoAdapter,
    "clip": ClipAdapter,
}
