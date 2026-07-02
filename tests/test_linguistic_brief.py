"""Brief indexes linguistic analysis from evidence."""

import json

from services.investigation_brief import empty_brief, finalize_brief_from_result


def test_finalize_brief_includes_linguistic():
    brief = empty_brief(query="alice")
    result = {
        "evidence_extraction": {
            "linguistic_analysis": {
                "language_profile": {"primary": "hinglish"},
                "topics": [{"topic": "technology", "score": 0.8, "evidence_snippets": ["hackathon dev"]}],
                "keywords": ["github", "hackathon"],
                "named_entities": [{"text": "https://github.com/alice", "kind": "url"}],
                "cross_links": [],
                "contradictions": [],
            }
        },
        "fusion": {},
        "correlation": {},
    }
    finalize_brief_from_result(brief, result)
    assert brief.get("linguistic_analysis") is not None
    assert any("linguistic" in s for s in brief["facts"]["snippets"])


def test_copilot_pack_preserves_linguistic_brief(tmp_path, monkeypatch):
    from services.copilot import build_copilot_pack_from_result
    from services.copilot_store import load_copilot_pack

    monkeypatch.setenv("COPILOT_DATA_DIR", str(tmp_path))

    inv_id = "ling-test-1"
    result = {
        "query": "manojyadavnr",
        "tool_results": [],
        "evidence_extraction": {
            "linguistic_analysis": {
                "artifacts_analyzed": 3,
                "language_profile": {"primary": "en"},
                "topics": [{"topic": "technology", "score": 0.7, "evidence_snippets": ["github"]}],
                "keywords": ["github"],
                "named_entities": [],
                "cross_links": [],
                "contradictions": [],
            }
        },
    }

    # Simulate incremental brief stub created mid-investigation.
    stub_path = tmp_path / f"{inv_id}.json"
    stub_path.write_text(
        json.dumps(
            {
                "investigation_id": inv_id,
                "query": "manojyadavnr",
                "raw_full": {},
                "investigation_brief": empty_brief(investigation_id=inv_id, query="manojyadavnr"),
            }
        )
    )

    build_copilot_pack_from_result(inv_id, result, query="manojyadavnr")
    pack = load_copilot_pack(inv_id)
    brief = (pack or {}).get("investigation_brief") or {}
    assert brief.get("linguistic_analysis") is not None
    assert any("[linguistic]" in str(s) for s in (brief.get("facts") or {}).get("snippets") or [])
