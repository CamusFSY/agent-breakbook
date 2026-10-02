import asyncio

import pytest

from breakbook.catalog import CASES
from breakbook.models import AdapterResult, Limits, Outcome
from breakbook.runner import run_trial
from breakbook.world import World


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("variant", ["broken", "fixed"])
@pytest.mark.parametrize("fault", [True, False])
async def test_control_matrix(case, variant, fault):
    trial = await run_trial(case, variant, fault=fault)
    expected = "fail" if fault and variant == "broken" else "pass"
    assert trial.verdict == expected, trial.model_dump()
    assert trial.state["pending"] == 0


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("repetition", range(20))
async def test_fixed_repeated(case, repetition):
    trial = await run_trial(case, index=repetition + 1)
    assert trial.verdict == "pass", trial.model_dump()


@pytest.mark.parametrize("case", CASES)
async def test_no_op_agent_cannot_pass(case):
    async def no_op(*args):
        return AdapterResult(outcome=Outcome(status="ok"))

    trial = await run_trial(case, adapter="custom", custom_runner=no_op)
    assert trial.verdict == "fail"
    assert not next(c for c in trial.checks if c.name == "work_attempted").passed


async def test_false_success_rejected_after_real_work():
    async def dishonest(case, variant, call, limits):
        await call("fetch_status", {})
        return AdapterResult(outcome=Outcome(status="ok"))

    trial = await run_trial("hung-tool", adapter="custom", custom_runner=dishonest)
    assert trial.verdict == "fail"
    assert [c.name for c in trial.checks if not c.passed] == ["honest_status"]


async def test_reject_everything_is_not_a_fix():
    async def reject(case, variant, call, limits):
        await call("send_notification", {"operation_id": "", "message": "Build finished"})
        return AdapterResult(outcome=Outcome(status="unavailable"))

    for fault in (True, False):
        trial = await run_trial("lost-ack", adapter="custom", custom_runner=reject, fault=fault)
        assert trial.verdict == "fail"


@pytest.mark.parametrize("case", ["hung-tool", "retry-storm"])
async def test_healthy_control_requires_real_task_completion(case):
    async def wrong_tool(case, variant, call, limits):
        await call("unrelated_tool", {})
        return AdapterResult(outcome=Outcome(status="ok"))

    trial = await run_trial(case, adapter="custom", custom_runner=wrong_tool, fault=False)
    assert trial.verdict == "fail"
    assert not next(c for c in trial.checks if c.name == "healthy_work_completed").passed


async def test_atomic_deduplication_and_payload_conflict():
    world = World("lost-ack", "fixed", Limits(max_tool_calls=20))
    arguments = {"operation_id": "same-job", "message": "hello"}
    replies = await asyncio.gather(*(world.call("send_notification", arguments) for _ in range(10)))
    assert len(world.state["outbox"]) == 1
    assert sum(r.get("error") == "ack_lost" for r in replies) == 1
    assert {r["receipt_id"] for r in replies if r["ok"]} == {"receipt-1"}
    conflict = await world.call("send_notification", {**arguments, "message": "different"})
    assert conflict == {"ok": False, "error": "idempotency_conflict"}
    other = await world.call("send_notification", {**arguments, "operation_id": "other-job"})
    assert other["ok"] and len(world.state["outbox"]) == 2


async def test_retry_boundary_is_exercised():
    trial = await run_trial("retry-storm")
    assert trial.state["provider_attempts"] == 3
    assert trial.state["calls"] == 4
    assert any(e["kind"] == "boundary.retry_limit" for e in trial.state["events"])


async def test_custom_runner_is_required():
    with pytest.raises(ValueError, match="custom_runner"):
        await run_trial("lost-ack", adapter="custom")


async def test_adapter_failure_is_infrastructure_error():
    async def crashed(*args):
        raise RuntimeError("a secret should not be persisted")

    trial = await run_trial("lost-ack", adapter="custom", custom_runner=crashed)
    assert trial.verdict == "infra_error"
    assert trial.result.error == "RuntimeError"
    assert "secret" not in trial.model_dump_json()


@pytest.mark.parametrize("settings", [{"tool_timeout": 1, "watchdog": 0.1}, {"retry_attempts": 8}])
def test_invalid_limits(settings):
    with pytest.raises(ValueError):
        Limits(**settings)
