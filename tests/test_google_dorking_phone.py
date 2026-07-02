"""Google dorking adapter regression tests."""

import pytest

from adapters.google_dorking import GoogleDorkingAdapter


@pytest.mark.asyncio
async def test_run_dorks_does_not_recurse():
    adapter = GoogleDorkingAdapter()
    result = await adapter.run("919164873661", timeout=20)
    assert "RecursionError" not in (result.error or "")
