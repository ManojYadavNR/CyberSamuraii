"""Username scan caps — prevent OOM on full Maigret inventory."""

from adapters.scan_config import maigret_max_sites, sherlock_max_sites
from adapters.site_lists import cap_site_list, estimated_username_sites, maigret_site_names, sherlock_site_names


def test_maigret_site_cap_standard():
    all_sites = maigret_site_names()
    if len(all_sites) <= 100:
        return
    capped, _priority = cap_site_list(all_sites, maigret_max_sites())
    assert len(capped) <= (maigret_max_sites() or len(all_sites))
    assert len(capped) < len(all_sites)


def test_estimated_username_sites_is_bounded():
    total = estimated_username_sites()
    assert 0 < total < 2000


def test_sherlock_site_cap():
    sites = sherlock_site_names()
    if not sites:
        return
    capped, _priority = cap_site_list(sites, sherlock_max_sites())
    assert len(capped) <= (sherlock_max_sites() or len(sites))
