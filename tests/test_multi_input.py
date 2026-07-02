"""Tests for multi-input parsing."""

from services.multi_input import parse_investigation_input
from services.query_detector import detect_query_type


def test_single_username():
    p = parse_investigation_input("manojyadavnr")
    assert p.username == "manojyadavnr"
    assert p.primary_type == "username"
    assert not p.is_multi


def test_single_email():
    p = parse_investigation_input("alice@example.com")
    assert p.email == "alice@example.com"
    assert detect_query_type("alice@example.com") == "email"


def test_multi_username_email_occupation():
    p = parse_investigation_input("manojyadavnr | alice@example.com | occupation: software engineer")
    assert p.is_multi
    assert p.username == "manojyadavnr"
    assert p.email == "alice@example.com"
    assert p.occupation == "software engineer"
    assert detect_query_type(p.raw) == "multi"


def test_kv_format():
    p = parse_investigation_input("username: jdoe | email: jdoe@corp.com | name: John Doe")
    assert p.username == "jdoe"
    assert p.email == "jdoe@corp.com"
    assert p.name == "John Doe"


def test_dork_query_combines_fields():
    p = parse_investigation_input("username: manoj | occupation: analyst | name: Manoj Yadav")
    q = p.dork_query()
    assert "manoj" in q.lower()
    assert "analyst" in q.lower()
