from adapters.holehe import HoleheAdapter
from adapters.image_intel import ImageIntelAdapter
from adapters.maigret import MaigretAdapter
from adapters.recon_ng import ReconNgAdapter
from adapters.shodan_adapter import ShodanAdapter
from adapters.sherlock import SherlockAdapter
from adapters.social_analyzer import SocialAnalyzerAdapter
from adapters.spiderfoot import SpiderFootAdapter
from adapters.theharvester import TheHarvesterAdapter
from adapters.whatsmyname import WhatsMyNameAdapter
from adapters.base import BaseAdapter

FEATURE_TOOLS: dict[str, list[str]] = {
    "username_search": ["sherlock", "maigret", "whatsmyname", "social_analyzer"],
    "email_intel": ["holehe", "theharvester", "spiderfoot"],
    "domain_intel": ["theharvester", "spiderfoot", "recon_ng"],
    "infra_intel": ["shodan"],
    "image_intel": ["image_intel"],
}

ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "sherlock": SherlockAdapter,
    "maigret": MaigretAdapter,
    "whatsmyname": WhatsMyNameAdapter,
    "social_analyzer": SocialAnalyzerAdapter,
    "holehe": HoleheAdapter,
    "theharvester": TheHarvesterAdapter,
    "spiderfoot": SpiderFootAdapter,
    "recon_ng": ReconNgAdapter,
    "shodan": ShodanAdapter,
    "image_intel": ImageIntelAdapter,
}

DEFAULT_TIMEOUTS: dict[str, float] = {
    "username_search": 180.0,
    "email_intel": 120.0,
    "domain_intel": 180.0,
    "infra_intel": 60.0,
    "image_intel": 60.0,
}
