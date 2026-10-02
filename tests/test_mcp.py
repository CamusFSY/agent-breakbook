from contextlib import asynccontextmanager

import pytest

from breakbook.catalog import CASES
from breakbook.models import Limits
from breakbook.runner import run_trial
from breakbook.world import World


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("variant", ["broken", "fixed"])
@pytest.mark.parametrize("fault", [True, False])
async def test_real_stdio_roundtrip(case, variant, fault):
    trial = await run_trial(
        case, variant, fault=fault, adapter="scripted-mcp", limits=Limits(watchdog=1)
    )
    expected = "fail" if fault and variant == "broken" else "pass"
    assert trial.verdict == expected, trial.model_dump()
    assert trial.transport == "mcp-stdio"
    assert trial.evidence == "scripted"
    assert trial.state["pending"] == 0, trial.state


async def test_mcp_deadline_is_application_control():
    trial = await run_trial("hung-tool", adapter="scripted-mcp", limits=Limits(watchdog=1))
    assert trial.result.termination == "completed"
    kinds = [e["kind"] for e in trial.state["events"]]
    assert kinds.index("tool.cleaned_up") < kinds.index("boundary.deadline")


async def test_transport_failure_retains_committed_evidence(monkeypatch):
    @asynccontextmanager
    async def failing_transport(case, variant, limits, fault, ledger):
        world = World(case, variant, limits, fault=fault, ledger=ledger)
        yield world.call
        raise RuntimeError("transport closed unexpectedly")

    monkeypatch.setattr("breakbook.runner.mcp_call", failing_transport)
    trial = await run_trial("lost-ack", adapter="scripted-mcp")
    assert trial.verdict == "infra_error"
    assert len(trial.state["outbox"]) == 1
    assert trial.state["fault_triggered"]
