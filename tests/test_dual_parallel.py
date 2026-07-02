"""Dual username+email parallel branch settings."""

import pytest

from services.multi_input import parse_investigation_input
from services.resource_guard import DUAL_BRANCH_PARALLEL, MULTI_INPUT_PARALLEL


def test_multi_input_defaults_enabled():
    assert MULTI_INPUT_PARALLEL is True
    assert DUAL_BRANCH_PARALLEL is True


def test_dual_parse():
    p = parse_investigation_input("ManojYadavNR | manojmanu938055@gmail.com")
    assert p.is_multi
    assert p.username == "ManojYadavNR"
    assert p.email == "manojmanu938055@gmail.com"


@pytest.mark.asyncio
async def test_dual_branch_parallel_emits_mode(monkeypatch):
    from schemas.common import FeatureResult
    from schemas.fusion import FusionOutput
    from services.investigation_runner import InvestigationRunner

    runner = InvestigationRunner()
    parsed = parse_investigation_input("user1 | u1@example.com")
    emitted: list[dict] = []

    async def emit(msg):
        emitted.append(msg)

    async def fake_username(*args, **kwargs):
        return FeatureResult(
            feature="username_search",
            query="user1",
            fusion=FusionOutput(deduplicated_entities=[], entities=[]),
        )

    async def fake_email(*args, **kwargs):
        return FeatureResult(
            feature="email_intel",
            query="u1@example.com",
        )

    monkeypatch.setattr(runner, "_run_with_progress", fake_username)
    monkeypatch.setattr(runner, "_run_email", fake_email)

    await runner._run_multi_input(parsed, 60.0, emit)

    modes = [m.get("mode") for m in emitted if m.get("phase") == "multi_input"]
    assert "dual_parallel" in modes
