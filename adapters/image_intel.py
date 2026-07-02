import os
import asyncio
from pathlib import Path

import httpx

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class ImageIntelAdapter(BaseAdapter):
    """Pipeline hooks for reverse image search and metadata extraction."""

    name = "image_intel"
    default_timeout = 60.0

    async def _execute(self, query: str) -> ToolResult:
        results: list[dict] = []

        image_path = query if os.path.isfile(query) else None
        image_url = query if query.startswith("http") else None

        if image_path:
            metadata = await asyncio.to_thread(self._extract_metadata_sync, image_path)
            results.append(
                self._normalize_entry(
                    platform="metadata_extraction",
                    extra=metadata,
                )
            )

        reverse_results = await self._reverse_image_search_placeholder(image_url or image_path)
        results.extend(reverse_results)

        return ToolResult(
            tool=self.name,
            success=True,
            data=results,
            raw_output=f"Image intel pipeline: {len(results)} results",
        )

    def _extract_metadata_sync(self, image_path: str) -> dict:
        metadata: dict = {"source": "exif_extraction", "file": image_path}
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS

            with Image.open(image_path) as img:
                metadata["format"] = img.format
                metadata["size"] = {"width": img.width, "height": img.height}
                metadata["mode"] = img.mode
                exif = img._getexif() or {}
                exif_data = {}
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if isinstance(value, bytes):
                        value = value.decode(errors="replace")[:200]
                    exif_data[str(tag)] = value
                metadata["exif"] = exif_data
            try:
                import piexif

                exif_dict = piexif.load(image_path)
                if exif_dict.get("GPS"):
                    metadata["gps_present"] = True
            except Exception:
                pass
        except Exception as exc:
            metadata["error"] = str(exc)
        return metadata

    async def _extract_metadata(self, image_path: str) -> dict:
        return await asyncio.to_thread(self._extract_metadata_sync, image_path)

    async def _reverse_image_search_placeholder(
        self, source: str | None
    ) -> list[dict]:
        """Placeholder hooks for reverse image search APIs."""
        placeholders = [
            {
                "platform": "google_reverse_image",
                "status": "placeholder",
                "api_endpoint": "https://lens.google.com/upload",
                "note": "Integrate Google Lens / Custom Search API",
            },
            {
                "platform": "tineye",
                "status": "placeholder",
                "api_endpoint": "https://api.tineye.com/rest/",
                "note": "Integrate TinEye API with TINEYE_API_KEY",
            },
            {
                "platform": "yandex_images",
                "status": "placeholder",
                "api_endpoint": "https://yandex.com/images/search",
                "note": "Integrate Yandex Image Search API",
            },
        ]

        results = []
        for ph in placeholders:
            entry = self._normalize_entry(
                platform=ph["platform"],
                extra={
                    **ph,
                    "source": source,
                    "ready_for_integration": True,
                },
            )
            results.append(entry)

        if source and source.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.head(source, follow_redirects=True)
                    results.append(
                        self._normalize_entry(
                            platform="image_url_probe",
                            url=source,
                            extra={
                                "status_code": resp.status_code,
                                "content_type": resp.headers.get("content-type"),
                                "content_length": resp.headers.get("content-length"),
                            },
                        )
                    )
            except Exception as e:
                results.append(
                    self._normalize_entry(
                        platform="image_url_probe",
                        url=source,
                        extra={"error": str(e)},
                    )
                )

        return results
