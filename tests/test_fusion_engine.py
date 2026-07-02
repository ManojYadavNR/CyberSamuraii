"""Unit tests for the SOCMINT Data Fusion Engine."""

import unittest

from schemas.common import ToolResult
from services.fusion_engine import (
    DataFusionEngine,
    apply_account_corroboration,
    deduplicate_entities,
    entity_key,
    is_confirmed_account,
    normalize_url,
)
from services.fusion_engine import Entity, _extract_from_item, _score_entity


def _tool(name: str, data: list[dict]) -> ToolResult:
    return ToolResult(tool=name, success=True, data=data)


class TestNormalization(unittest.TestCase):
    def test_normalize_url_strips_www_and_trailing_slash(self):
        assert normalize_url("https://www.GitHub.com/User/") == "github.com/user"

    def test_entity_key_format(self):
        assert entity_key("account", "github.com/user") == "account:github.com/user"


class TestDeduplication(unittest.TestCase):
    def test_merge_duplicate_urls_from_sherlock_and_maigret(self):
        engine = DataFusionEngine()
        url = "https://github.com/testuser"
        norm = normalize_url(url)

        results = [
            _tool(
                "sherlock",
                [
                    {
                        "platform": "GitHub",
                        "url": url,
                        "source_tool": "sherlock",
                        "verified": False,
                        "check_type": "username_probe",
                        "status": "unconfirmed",
                    }
                ],
            ),
            _tool(
                "maigret",
                [
                    {
                        "platform": "GitHub",
                        "url": url,
                        "source_tool": "maigret",
                        "verified": True,
                        "check_type": "live_scan",
                        "status": "maigret_claimed",
                    }
                ],
            ),
        ]

        output = engine.fuse(results, "username_search", "testuser")
        accounts = [e for e in output.deduplicated_entities if e.type == "account"]
        github = [e for e in accounts if norm in e.value]

        assert len(github) == 1
        assert set(github[0].sources) == {"maigret", "sherlock"}
        assert github[0].metadata.get("verified") is True
        assert github[0].metadata.get("corroboration_status") == "confirmed"
        assert github[0].fusion_score > 0
        assert "multi_source_corroboration" in output.evidence_map[entity_key("account", github[0].value)]["signals"]
        assert "username_cross_validation" in output.evidence_map[entity_key("account", github[0].value)]["signals"]

    def test_social_analyzer_dataset_lower_score_than_live_scan(self):
        engine = DataFusionEngine()
        results = [
            _tool(
                "social_analyzer",
                [
                    {
                        "platform": "Instagram",
                        "url": "https://instagram.com/testuser",
                        "source_tool": "social_analyzer",
                        "verified": False,
                        "check_type": "dataset_lookup",
                    }
                ],
            ),
            _tool(
                "sherlock",
                [
                    {
                        "platform": "Instagram",
                        "url": "https://instagram.com/testuser",
                        "source_tool": "sherlock",
                        "verified": False,
                        "check_type": "username_probe",
                        "status": "unconfirmed",
                    }
                ],
            ),
        ]

        output = engine.fuse(results, "username_search", "testuser")
        account = next(e for e in output.deduplicated_entities if "instagram.com" in e.value)
        assert "sherlock" in account.sources
        assert "social_analyzer" in account.sources
        assert account.metadata.get("verified") is False
        assert account.metadata.get("corroboration_status") in {"probe", "unconfirmed"}
        assert not is_confirmed_account(account)

    def test_sherlock_only_stays_unconfirmed_after_live_verify(self):
        entity = Entity(
            type="account",
            value="github.com:testuser",
            sources=["sherlock"],
            metadata={
                "url": "https://github.com/testuser",
                "platform": "github.com",
                "check_type": "username_probe",
                "live_profile_verified": True,
                "content_seed_verified": True,
                "live_verify_reason": "ok",
            },
        )
        confirmed = apply_account_corroboration([entity], seed_query="testuser")[0]
        assert confirmed.metadata.get("verified") is False
        assert not is_confirmed_account(confirmed)

    def test_definitive_verify_failure_blocks_two_tool_agreement(self):
        entity = Entity(
            type="account",
            value="mastodon.cloud:fake",
            sources=["maigret", "social_analyzer"],
            metadata={
                "url": "https://mastodon.cloud/fakeuser",
                "platform": "mastodon.cloud",
                "live_profile_verified": False,
                "live_verify_reason": "junk_profile_url",
            },
        )
        confirmed = apply_account_corroboration([entity])[0]
        assert confirmed.metadata.get("verified") is False
        assert not is_confirmed_account(confirmed)

    def test_sherlock_only_stays_unconfirmed(self):
        engine = DataFusionEngine()
        results = [
            _tool(
                "sherlock",
                [
                    {
                        "platform": "Reddit",
                        "url": "https://reddit.com/user/testuser",
                        "source_tool": "sherlock",
                        "verified": False,
                        "check_type": "username_probe",
                        "status": "unconfirmed",
                    }
                ],
            ),
        ]
        output = engine.fuse(results, "username_search", "testuser")
        account = next(e for e in output.deduplicated_entities if "reddit.com" in e.value)
        assert account.metadata.get("verified") is False
        assert account.metadata.get("corroboration_status") == "probe"
        assert not is_confirmed_account(account)

    def test_metadata_not_lost_on_merge(self):
        a = Entity(
            type="email",
            value="user@example.com",
            sources=["holehe"],
            metadata={"registered": True, "platform": "twitter.com"},
        )
        b = Entity(
            type="email",
            value="user@example.com",
            sources=["spiderfoot"],
            metadata={"data_type": "Email Address", "module": "sfp_email"},
        )
        merged = deduplicate_entities([a, b])
        assert len(merged) == 1
        assert set(merged[0].sources) == {"holehe", "spiderfoot"}
        assert merged[0].metadata["registered"] is True
        assert "source_details" in merged[0].metadata


class TestEntityExtraction(unittest.TestCase):
    def test_holehe_registered_account(self):
        items = _extract_from_item(
            {
                "platform": "twitter.com",
                "source_tool": "holehe",
                "email": "user@test.com",
                "status": "registered",
                "registered": True,
            },
            "holehe",
            "user@test.com",
            "email_intel",
        )
        assert any(i.type == "account" for i in items)
        assert any(i.type == "email" for i in items)

    def test_skip_internal_summary(self):
        items = _extract_from_item(
            {"platform": "_scan_summary", "email": "x@y.com"},
            "holehe",
            "x@y.com",
            "email_intel",
        )
        assert items == []

    def test_email_domain_enrichment_boost(self):
        engine = DataFusionEngine()
        results = [
            _tool(
                "theharvester",
                [
                    {
                        "platform": "email",
                        "source_tool": "theharvester",
                        "email": "contact@acme.com",
                    }
                ],
            ),
            _tool(
                "spiderfoot",
                [
                    {
                        "platform": "email",
                        "source_tool": "spiderfoot",
                        "email": "contact@acme.com",
                        "data_type": "Email Address",
                    }
                ],
            ),
        ]
        output = engine.fuse(results, "email_intel", "contact@acme.com")
        email_entity = next(e for e in output.deduplicated_entities if e.type == "email")
        assert set(email_entity.sources) == {"spiderfoot", "theharvester"}
        signals = output.evidence_map[entity_key("email", "contact@acme.com")]["signals"]
        assert "email_domain_enrichment" in signals


class TestScoring(unittest.TestCase):
    def test_live_scan_scores_higher_than_probe(self):
        live = Entity(
            type="account",
            value="github.com:user",
            sources=["maigret"],
            metadata={"verified": True, "check_type": "live_scan", "corroboration_status": "confirmed"},
        )
        probe = Entity(
            type="account",
            value="instagram.com:user",
            sources=["sherlock"],
            metadata={"verified": False, "check_type": "username_probe", "corroboration_status": "probe"},
        )
        live_r, live_f = _score_entity(live)
        probe_r, probe_f = _score_entity(probe)
        assert live_f > probe_f

    def test_holehe_only_not_confirmed_without_seed_email(self):
        from services.fusion_engine import Entity, is_confirmed_account

        entity = Entity(
            type="account",
            value="github.com:manojy5951@gmail.com",
            sources=["holehe"],
            metadata={"registered": True, "email": "manojy5951@gmail.com", "platform": "github.com"},
        )
        assert not is_confirmed_account(entity)

    def test_holehe_confirmed_when_seed_email_matches(self):
        from services.fusion_engine import Entity, is_confirmed_account

        entity = Entity(
            type="account",
            value="github.com:manojy5951@gmail.com",
            sources=["holehe"],
            metadata={
                "registered": True,
                "email": "manojy5951@gmail.com",
                "platform": "github.com",
                "status": "registered",
            },
        )
        assert is_confirmed_account(entity, seed_email="manojy5951@gmail.com")

    def test_fusion_output_schema(self):
        engine = DataFusionEngine()
        output = engine.fuse([], "username_search", "nobody")
        assert output.entities == []
        assert output.deduplicated_entities == []
        assert output.fusion_score == 0.0
        assert output.evidence_map == {}


if __name__ == "__main__":
    unittest.main()
