"""Handle extraction from query-string profile URLs."""

from services.correlation.handle_quality import normalize_profile_handle


def test_forum_member_php_username_query():
    url = "https://forum.igromania.ru/member.php?username=ManojYadavNR"
    handle = normalize_profile_handle(url, "forum.igromania.ru", {})
    assert handle == "manojyadavnr"


def test_imgur_user_path_skips_generic_segment():
    url = "https://imgur.com/user/ManojYadavNR"
    handle = normalize_profile_handle(url, "imgur.com", {"username": "user"})
    assert handle == "manojyadavnr"
