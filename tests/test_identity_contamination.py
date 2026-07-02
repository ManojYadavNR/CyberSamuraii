"""Identity contamination guards — wrong-person merge prevention."""

from services.discovery.attribution import (
    context_references_seed,
    dork_hit_attributed,
    email_local_matches_seed,
    url_references_seed,
)
from services.evidence.document_parser import parse_dork_document
from services.google_dorking.filters import is_junk_dork_url


def test_different_manoj_not_attributed():
    """Generic 'Manoj Yadav' without seed handle must not match ManojYadavNR."""
    assert not context_references_seed(
        "Manoj Yadav MS Computer Science at University of Southern California",
        seed_query="ManojYadavNR",
    )


def test_full_handle_in_text_attributed():
    assert context_references_seed(
        "Manoj Yadav N R MERN STACK DEVELOPER",
        seed_query="ManojYadavNR",
    )


def test_wrong_github_url_not_attributed():
    assert not dork_hit_attributed(
        url="https://github.com/man007yadav",
        title="Manoj Yadav - GitHub",
        snippet="MS Computer Science @ USC",
        seed_query="ManojYadavNR",
    )


def test_wrong_email_not_linked():
    assert not email_local_matches_seed("manojy5951@gmail.com", "ManojYadavNR")
    assert email_local_matches_seed("manojyadavnr@gmail.com", "ManojYadavNR")


def test_junk_dork_domains_filtered():
    assert is_junk_dork_url("https://wheelofnames.com/")
    assert is_junk_dork_url("https://en.wikipedia.org/wiki/Manoj_Yadava")


def test_unrelated_linkedin_not_parsed():
    fields = parse_dork_document(
        {
            "title": "Manoj Yadav - University of Southern California",
            "snippet": "Graduate student in Los Angeles",
            "url": "https://github.com/man007yadav",
            "dork_category": "social_github",
            "check_type": "google_dork",
        },
        entity_value="https://github.com/man007yadav",
        seed_query="ManojYadavNR",
    )
    assert fields == []


def test_wrong_facebook_profile_rejected():
    from services.discovery.attribution import is_garbage_serp_bundle, profile_handle_conflicts_seed

    assert profile_handle_conflicts_seed("https://www.facebook.com/DrMohanYadav51/", "ManojYadavNR")
    assert profile_handle_conflicts_seed("https://www.instagram.com/manoj__sir/", "ManojYadavNR")
    assert not profile_handle_conflicts_seed(
        "https://www.facebook.com/cit.nc/photos/congratulations-to-manoj-yadav-nr-kirana/",
        "ManojYadavNR",
    )


def test_instagram_post_requires_seed_in_content_not_dork_query_only():
    from services.discovery.attribution import dork_hit_attributed

    assert not dork_hit_attributed(
        url="https://www.instagram.com/p/DIOMeMWp5Hx/",
        title="",
        snippet="",
        seed_query="ManojYadavNR",
        dork_query='site:instagram.com "Manoj Yadav NR" hackathon',
        dork_category="social_post_search",
    )
    assert dork_hit_attributed(
        url="https://www.instagram.com/p/DIOMeMWp5Hx/",
        title="Manoj Yadav NR hackathon win",
        snippet="",
        seed_query="ManojYadavNR",
        dork_query='site:instagram.com "Manoj Yadav NR" hackathon',
        dork_category="social_post_search",
    )


def test_wrong_facebook_post_not_attributed_via_dork_query():
    from services.discovery.attribution import dork_hit_attributed

    assert not dork_hit_attributed(
        url="https://www.facebook.com/cit.nc/posts/congratulations-to-ganesh-jaishi-shreya-pal-vaishnavi-and-pooja-aon-winning-the-/1",
        title="Congratulations to Ganesh Jaishi",
        snippet="hackathon winners",
        seed_query="ManojYadavNR",
        dork_query='site:facebook.com "Manoj Yadav NR" hackathon',
        dork_category="social_post_search",
    )


def test_wrong_facebook_post_rejected_even_when_snippet_mentions_seed():
    from services.discovery.attribution import dork_hit_attributed

    assert not dork_hit_attributed(
        url="https://www.facebook.com/cit.nc/posts/congratulations-to-ganesh-jaishi-shreya-pal-vaishnavi-and-pooja-son-winning-the-/1201841691950680/",
        title="Cambridge Institute of Technology North Campus",
        snippet=(
            "Congratulations to Manoj Yadav NR, Kirana GV, Mahanthesh SK, Mahendra DM "
            "on becoming the runners-up in HackToFuture 3.0."
        ),
        seed_query="ManojYadavNR",
        dork_query='"Manoj Yadav NR" HackToFuture 3.0',
        dork_category="social_post_search",
    )
    assert dork_hit_attributed(
        url="https://www.facebook.com/cit.nc/photos/congratulations-to-manoj-yadav-nr-kirana-gv-mahanthesh-sk-mahendra-dm-on-becomin/1201842195283963/",
        title="Cambridge - Congratulations to Manoj Yadav NR",
        snippet="Runners-up in HackToFuture 3.0",
        seed_query="ManojYadavNR",
        dork_query='"Manoj Yadav NR" HackToFuture 3.0',
        dork_category="social_post_search",
    )


def test_garbled_serp_bundle_rejected():
    from services.discovery.attribution import dork_hit_attributed, is_garbage_serp_bundle

    title = (
        "Dr Mohan Yadav - FacebookManoj Rajput (@manoj__sir) • Instagram photos and videos"
        "Best Advertisement ever-Winner of Best Ad 2014 - YouTubeWheel of Names"
    )
    assert is_garbage_serp_bundle(title)
    assert not dork_hit_attributed(
        url="https://www.facebook.com/DrMohanYadav51/",
        title=title,
        snippet="Chief Minister of Madhya Pradesh",
        seed_query="ManojYadavNR",
    )
