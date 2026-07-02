"""Tests for direct platform HTTP probing."""

from services.platform_probe import classify_probe_response


def test_login_wall_counts_as_existing_profile():
    html = """
    <html><head><title>LinkedIn</title></head>
    <body>Sign in to continue viewing this profile. Join LinkedIn to see full profiles.
    """ + ("padding " * 40) + """
    </body></html>
    """
    exists, reason = classify_probe_response(
        "https://www.linkedin.com/in/alice",
        200,
        html,
    )
    assert exists is True
    assert reason in {"login_wall", "ok"}


def test_not_found_profile_rejected():
    html = "<html><title>Not Found</title><body>Sorry, this page isn't available</body></html>"
    exists, reason = classify_probe_response(
        "https://www.instagram.com/nobodyhere/",
        404,
        html,
    )
    assert exists is False
