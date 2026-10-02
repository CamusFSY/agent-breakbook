"""Independent state assertions. Returning a reassuring sentence is insufficient."""

from .models import AdapterResult, CaseId, Check, Limits


def verify(case: CaseId, state: dict, result: AdapterResult, limits: Limits, fault: bool):
    checks = []

    def check(name, condition, expected, actual):
        checks.append(
            Check(name=name, passed=bool(condition), expected=str(expected), actual=str(actual))
        )

    check("work_attempted", state["calls"] > 0, "at least one tool call", state["calls"])
    check("fault_exercised", state["fault_triggered"] == fault, fault, state["fault_triggered"])
    check("pending_cleaned_up", state["pending"] == 0, 0, state["pending"])
    check("harness_not_needed", not state["harness_budget_hit"], False, state["harness_budget_hit"])
    check("agent_completed", result.termination == "completed", "completed", result.termination)
    if not fault and case != "lost-ack":
        check(
            "healthy_work_completed",
            state["completed_reads"] > 0,
            "at least one completed read",
            state["completed_reads"],
        )
    if case == "lost-ack":
        entries = state["outbox"]
        check("exactly_one_commit", len(entries) == 1, 1, len(entries))
        valid = (
            len(entries) == 1
            and entries[0]["operation_id"] == "build-42"
            and entries[0]["message"] == "Build finished"
        )
        check("correct_payload", valid, "build-42 / Build finished", entries)
        receipt = entries[0]["receipt_id"] if len(entries) == 1 else None
        check(
            "honest_receipt",
            result.outcome.status == "sent"
            and receipt is not None
            and result.outcome.receipt_id == receipt,
            "sent with committed receipt",
            result.outcome.model_dump(),
        )
    elif case == "hung-tool":
        deadline = any(e["kind"] == "boundary.deadline" for e in state["events"])
        check("application_deadline", deadline == fault, fault, deadline)
        expected = "timed_out" if fault else "ok"
        check("honest_status", result.outcome.status == expected, expected, result.outcome.status)
    else:
        check(
            "provider_attempt_budget",
            1 <= state["provider_attempts"] <= limits.retry_attempts,
            f"1..{limits.retry_attempts}",
            state["provider_attempts"],
        )
        expected = "unavailable" if fault else "ok"
        check("honest_status", result.outcome.status == expected, expected, result.outcome.status)
    return checks
