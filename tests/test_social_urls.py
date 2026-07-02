"""Tests for social URL normalization."""

from services.social_urls import external_visit_url, fix_facebook_post_url


def test_fix_malformed_facebook_photo_slug():
    bad = (
        "https://www.facebook.com/cit.nc/photos/a.congratulations-to-manoj-yadav-nr"
        "-kirana-gv-mahanthesh-sk-mahendra-dm-on-becomin/1201842195283963/"
    )
    fixed = fix_facebook_post_url(bad)
    assert "/photos/a.congratulations" not in fixed
    assert "/photos/congratulations-to-manoj-yadav-nr" in fixed


def test_numeric_facebook_album_unchanged():
    good = "https://www.facebook.com/cit.nc/photos/a.145292770223443/145288000223920/"
    assert fix_facebook_post_url(good) == good


def test_external_visit_url_adds_scheme():
    assert external_visit_url("facebook.com/cit.nc") is None
