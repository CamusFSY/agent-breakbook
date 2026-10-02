"""Deterministic bad/good control flows, not measurements of a language model."""

from collections.abc import Awaitable, Callable

from ..models import AdapterResult, CaseId, Limits, Outcome, Variant

ToolCall = Callable[[str, dict], Awaitable[dict]]


async def run_scripted(
    case: CaseId, variant: Variant, call: ToolCall, limits: Limits
) -> AdapterResult:
    if case == "lost-ack":
        # Keep the same business ID in both controls. The service boundary is the fix.
        for _ in range(2):
            reply = await call(
                "send_notification", {"operation_id": "build-42", "message": "Build finished"}
            )
            if reply["ok"]:
                return AdapterResult(outcome=Outcome(status="sent", receipt_id=reply["receipt_id"]))
        return AdapterResult(outcome=Outcome(status="unknown"))
    if case == "hung-tool":
        reply = await call("fetch_status", {})
        return AdapterResult(outcome=Outcome(status="ok" if reply["ok"] else "timed_out"))
    # Identical retrying client in both profiles: the boundary enforces the fix.
    for _ in range(limits.max_tool_calls + 1):
        reply = await call("read_inventory", {})
        if reply["ok"]:
            return AdapterResult(outcome=Outcome(status="ok"))
        if reply["error"] == "harness_budget":
            return AdapterResult(termination="harness_budget")
        if reply["error"] == "retry_limit":
            return AdapterResult(outcome=Outcome(status="unavailable"))
    return AdapterResult(outcome=Outcome(status="unavailable"))
