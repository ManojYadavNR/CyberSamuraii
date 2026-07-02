import os

from adapters.external_osint import EXTERNAL_OSINT_ADAPTERS
from adapters.google_dorking import GoogleDorkingAdapter
from adapters.platform_probe import PlatformProbeAdapter
from adapters.phone_social_intel import PhoneSocialIntelAdapter
from adapters.holehe import HoleheAdapter
from adapters.image_intel import ImageIntelAdapter
from adapters.image_tools import IMAGE_ADAPTER_CLASSES
from adapters.maigret import MaigretAdapter
from adapters.recon_ng import ReconNgAdapter
from adapters.shodan_adapter import ShodanAdapter
from adapters.sherlock import SherlockAdapter
from adapters.samurai import SamuraiAdapter
from adapters.social_analyzer import SocialAnalyzerAdapter
from adapters.spiderfoot import SpiderFootAdapter
from adapters.theharvester import TheHarvesterAdapter
from adapters.base import BaseAdapter
from orchestrator.parallel_config import IMAGE_PARALLEL_TOOLS
from services.osint_registry.router import tools_for_feature


def get_feature_tools(
    feature: str,
    *,
    profile: str = "fast",
    hop: bool = False,
    target: str = "",
) -> list[str]:
    """Registry-driven tool list — replaces hardcoded FEATURE_TOOLS."""
    return tools_for_feature(feature, profile=profile, hop=hop, target=target)


def feature_tools_snapshot() -> dict[str, list[str]]:
    """Materialized tool map for diagnostics/tests."""
    return {
        "username_search": get_feature_tools("username_search"),
        "email_intel": get_feature_tools("email_intel"),
        "domain_intel": get_feature_tools("domain_intel"),
        "infra_intel": get_feature_tools("infra_intel"),
        "image_intel": get_feature_tools("image_intel", profile="deep"),
    }


FEATURE_TOOLS: dict[str, list[str]] = feature_tools_snapshot()

ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "sherlock": SherlockAdapter,
    "maigret": MaigretAdapter,
    "social_analyzer": SocialAnalyzerAdapter,
    "holehe": HoleheAdapter,
    "theharvester": TheHarvesterAdapter,
    "spiderfoot": SpiderFootAdapter,
    "recon_ng": ReconNgAdapter,
    "shodan": ShodanAdapter,
    "image_intel": ImageIntelAdapter,
    "google_dorking": GoogleDorkingAdapter,
    "phone_social_intel": PhoneSocialIntelAdapter,
    "platform_probe": PlatformProbeAdapter,
    "samurai": SamuraiAdapter,
    **EXTERNAL_OSINT_ADAPTERS,
    **IMAGE_ADAPTER_CLASSES,
}

DEFAULT_TIMEOUTS: dict[str, float] = {
    "username_search": 180.0,
    "email_intel": 90.0,
    "domain_intel": 90.0,
    "infra_intel": 45.0,
    "image_intel": 300.0,
}

# Per-tool minimum budgets on CPU (first model load can take several minutes).
TOOL_TIMEOUTS: dict[str, float] = {
    "sherlock": 180.0,
    "maigret": 180.0,
    "social_analyzer": 280.0,
    "google_dorking": 300.0,
    "platform_probe": 35.0,
    "samurai": 360.0,
    "blackbird": 120.0,
    "nexfil": 90.0,
    "gitfive": 90.0,
    "ghunt": 90.0,
    "gravatar": 30.0,
    "phoneinfoga": 120.0,
    "phone_social_intel": 360.0,
    "subfinder": 90.0,
    "amass": 120.0,
    "dnsrecon": 90.0,
    "whois": 45.0,
    "holehe": 90.0,
    "theharvester": 90.0,
    "spiderfoot": 90.0,
    "insightface": 300.0,
    "deepface": 300.0,
    "tesseract": 120.0,
    "yolo": 180.0,
    "paddleocr": 180.0,
    "easyocr": 180.0,
    "facenet": 300.0,
    "grounding_dino": 300.0,
    "clip": 240.0,
    "google_lens": 90.0,
    "bing_visual": 90.0,
    "yandex_images": 90.0,
    "tineye": 90.0,
    "image_intel": 300.0,
    "imagehash": 90.0,
    "opencv": 90.0,
    "opencv_face": 180.0,
    "pillow": 60.0,
    "exiftool": 60.0,
    "hachoir": 60.0,
}


def effective_tool_timeout(tool: str, feature_timeout: float, *, hop: bool = False) -> float:
    """Tool budget — hops use min() so slow tools cannot exceed the hop cap."""
    floor = TOOL_TIMEOUTS.get(tool, feature_timeout)
    if hop:
        return min(floor, feature_timeout)
    return max(floor, feature_timeout)


# Per-hop budget during discovery expansion (seconds).
HOP_TIMEOUT_CAP = float(os.getenv("HOP_TIMEOUT_CAP", "40"))
