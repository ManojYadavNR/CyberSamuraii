"""Attribution and document parsing — generic suspect fixtures only."""

from services.discovery.attribution import context_references_seed
from services.evidence.document_parser import parse_dork_document


def test_spaced_name_matches_when_handle_in_text():
    assert context_references_seed(
        "Congratulations to JaneRivera42 on NovaHack 2025",
        seed_query="JaneRivera42",
    )


def test_spaced_display_name_without_handle_not_attributed():
    assert not context_references_seed(
        "Congratulations to Jane Rivera on NovaHack 2025",
        seed_query="JaneRivera42",
    )


def test_dork_achievement_extracts_event_name_from_snippet():
    meta = {
        "title": "Congratulations to JaneRivera42, Alex Kim",
        "snippet": "runner-up in NovaHack 2025 competing against 750 teams",
        "url": "https://community.example.org/ExampleCollege/posts/123",
        "dork_category": "achievements",
        "check_type": "google_dork",
    }
    fields = parse_dork_document(meta, entity_value=meta["url"], seed_query="JaneRivera42")
    achievements = [v for f, v, _, _ in fields if f == "achievement"]
    assert achievements
    assert any("novahack" in a.lower() for a in achievements)


def test_profile_employer_extracted_from_title_pattern():
    meta = {
        "title": "Jane Rivera - Orion Systems International",
        "snippet": "software engineer skilled in distributed systems",
        "url": "https://profiles.example.org/in/jane-rivera-42",
        "dork_category": "profile_exact",
        "check_type": "google_dork",
    }
    fields = parse_dork_document(meta, entity_value=meta["url"], seed_query="JaneRivera42")
    orgs = [v for f, v, _, _ in fields if f == "organization"]
    names = [v for f, v, _, _ in fields if f == "display_name"]
    assert any("orion systems" in o.lower() for o in orgs)
    assert any("jane rivera" in n.lower() for n in names)


def test_unrelated_suspect_not_attributed():
    meta = {
        "title": "Someone Else - Other Corp",
        "snippet": "winner of RandomFest 2024",
        "url": "https://profiles.example.org/in/someone-else",
        "dork_category": "profile_exact",
        "check_type": "google_dork",
    }
    fields = parse_dork_document(meta, entity_value=meta["url"], seed_query="JaneRivera42")
    assert fields == []
