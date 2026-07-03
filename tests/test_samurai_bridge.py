from services.multi_input import parse_investigation_input
from services.samurai_bridge import _username_from_query, instagram_session_configured
from services.username import normalize_username


def test_dual_input_scan_query_must_not_be_used_for_samurai():
    """normalize_username mangles pipe-separated seeds; Samurai needs the raw query."""
    seed = "ManojYadavNR | manojmanu938055@gmail.com"
    scan_query, _ = normalize_username(seed)
    assert scan_query != "manojyadavnr"
    assert parse_investigation_input(seed).username == "ManojYadavNR"
    assert _username_from_query(seed) == "manojyadavnr"
    assert _username_from_query(scan_query) != "manojyadavnr"


def test_username_from_query_lowercases_camelcase():
    assert _username_from_query("ManojYadavNR") == "manojyadavnr"


def test_username_from_query_parses_multi_input():
    assert _username_from_query("ManojYadavNR | manoj@test.com | name: Manoj Yadav NR") == "manojyadavnr"


def test_username_from_query_parses_spaced_name():
    assert _username_from_query("Manoj Yadav NR") == "manojyadavnr"


def test_generate_username_variations_manojyadavnr():
    from samurai.main import generate_username_variations

    variants = generate_username_variations("manojyadavnr", limit=12)
    lowered = {v.lower() for v in variants}
    assert "manojyadavnr" in lowered
    assert "manojyadav" in lowered
    assert any("27" in v for v in variants)
    assert any("yadav" in v for v in variants)
    assert all(len(v) >= 3 for v in variants)


def test_instagram_session_configured_reads_env(monkeypatch):
    monkeypatch.delenv("IG_SESSIONID", raising=False)
    monkeypatch.delenv("IG_COOKIES_FILE", raising=False)
    assert instagram_session_configured() is False
    monkeypatch.setenv("IG_SESSIONID", "test-session-token")
    assert instagram_session_configured() is True
