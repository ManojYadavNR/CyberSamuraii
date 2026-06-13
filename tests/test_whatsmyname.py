"""Tests for WhatsMyName live verification logic."""

from adapters.whatsmyname import classify_whatsmyname_response


def test_classify_existing_account_by_string_and_code():
    site = {
        "e_code": 200,
        "e_string": "profile-info__profile-data__name",
        "m_code": 404,
        "m_string": "This is not the page you're looking for",
    }
    body = "<div class='profile-info__profile-data__name'>alice</div>"
    assert classify_whatsmyname_response(site, 200, body) is True


def test_classify_missing_account_by_miss_string():
    site = {
        "e_code": 200,
        "e_string": "profile-info__profile-data__name",
        "m_code": 404,
        "m_string": "This is not the page you're looking for",
    }
    body = "This is not the page you're looking for"
    assert classify_whatsmyname_response(site, 404, body) is False


def test_classify_missing_by_status_only():
    site = {"e_code": 200, "m_code": 404}
    assert classify_whatsmyname_response(site, 404, "") is False


def test_classify_inconclusive_when_signals_conflict():
    site = {
        "e_code": 200,
        "e_string": "found-marker",
        "m_code": 404,
        "m_string": "found-marker",
    }
    assert classify_whatsmyname_response(site, 200, "found-marker") is None
