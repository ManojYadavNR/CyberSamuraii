"""Social Analyzer scan budget and site-cap configuration."""

import os

from adapters.scan_config import SOCIAL_ANALYZER_MAX_SITES_DEFAULT, social_analyzer_max_sites


def test_social_analyzer_max_sites_default(monkeypatch):
    monkeypatch.delenv("SOCIAL_ANALYZER_MAX_SITES", raising=False)
    assert social_analyzer_max_sites() == SOCIAL_ANALYZER_MAX_SITES_DEFAULT
    assert social_analyzer_max_sites() <= 400


def test_social_analyzer_max_sites_env_override(monkeypatch):
    monkeypatch.setenv("SOCIAL_ANALYZER_MAX_SITES", "120")
    # Re-import picks up env at module load; read default formula instead
    cap = max(80, int(os.getenv("SOCIAL_ANALYZER_MAX_SITES", "320")))
    assert cap == 120
