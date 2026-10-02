"""Small local services with an independently readable state ledger.

These services never send notifications or contact an external inventory API.
The lost-ack fault is an application-level ambiguous error after commit, not a
TCP packet-loss emulator. Snapshots are evidence, not a security sandbox.
"""

import asyncio
import copy
import json
import os
from pathlib import Path

from .models import CaseId, Limits, Variant


class World:
    def __init__(
        self,
        case: CaseId,
        variant: Variant,
        limits: Limits,
        *,
        fault: bool = True,
        ledger: Path | None = None,
    ):
        self.case = case
        self.variant = variant
        self.limits = limits
        self.fault = fault
        self.ledger = ledger
        self.lock = asyncio.Lock()
        self.state = {
            "case": case,
            "variant": variant,
            "calls": 0,
            "attempted_calls": 0,
            "provider_attempts": 0,
            "completed_reads": 0,
            "pending": 0,
            "fault_triggered": False,
            "harness_budget_hit": False,
            "outbox": [],
            "operations": {},
            "events": [],
        }
        self.event("world.ready", "local fixture ready")

    def snapshot(self) -> dict:
        return copy.deepcopy(self.state)

    def event(self, kind: str, detail: str) -> None:
        self.state["events"].append(
            {"seq": len(self.state["events"]), "kind": kind, "detail": detail}
        )
        if self.ledger:
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.ledger.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state), encoding="utf-8")
            os.replace(temporary, self.ledger)

    async def call(self, name: str, arguments: dict) -> dict:
        self.state["attempted_calls"] += 1
        if self.state["calls"] >= self.limits.max_tool_calls:
            self.state["harness_budget_hit"] = True
            self.event("harness.budget", "tool-call safety ceiling reached")
            return {"ok": False, "error": "harness_budget"}
        self.state["calls"] += 1
        self.event("tool.request", name)
        if name == "send_notification" and self.case == "lost-ack":
            return await self._send(**arguments)
        if name == "lookup_notification" and self.case == "lost-ack":
            operation_id = arguments["operation_id"]
            record = self.state["operations"].get(operation_id)
            self.event("tool.response", "operation found" if record else "operation not found")
            return {"ok": True, "receipt_id": record}
        if name == "fetch_status" and self.case == "hung-tool":
            if self.variant == "fixed":
                try:
                    async with asyncio.timeout(self.limits.tool_timeout):
                        return await self._fetch()
                except TimeoutError:
                    self.event(
                        "boundary.deadline", "pending tool cancelled at application deadline"
                    )
                    return {"ok": False, "error": "tool_timeout"}
            return await self._fetch()
        if name == "read_inventory" and self.case == "retry-storm":
            if (
                self.variant == "fixed"
                and self.state["provider_attempts"] >= self.limits.retry_attempts
            ):
                self.event("boundary.retry_limit", "no further provider attempts allowed")
                return {"ok": False, "error": "retry_limit"}
            self.state["provider_attempts"] += 1
            if self.fault:
                self.state["fault_triggered"] = True
                self.event("fault.rate_limit", "simulated provider unavailable")
                return {"ok": False, "error": "rate_limit", "retry_after_ms": 1}
            self.state["completed_reads"] += 1
            self.event("tool.response", "inventory available")
            return {"ok": True, "available": 7}
        self.event("tool.error", "unknown tool")
        return {"ok": False, "error": "unknown_tool"}

    async def _send(self, operation_id: str, message: str) -> dict:
        if not operation_id or len(operation_id) > 128 or len(message) > 1000:
            return {"ok": False, "error": "invalid_arguments"}
        async with self.lock:
            receipt = self.state["operations"].get(operation_id)
            if receipt and self.variant == "fixed":
                original = next(x for x in self.state["outbox"] if x["receipt_id"] == receipt)
                if original["message"] != message:
                    self.event("boundary.conflict", "operation ID reused with a different payload")
                    return {"ok": False, "error": "idempotency_conflict"}
                self.event("boundary.deduplicated", receipt)
                return {"ok": True, "receipt_id": receipt}
            receipt = f"receipt-{len(self.state['outbox']) + 1}"
            self.state["outbox"].append(
                {"operation_id": operation_id, "message": message, "receipt_id": receipt}
            )
            self.state["operations"][operation_id] = receipt
            self.event("state.commit", f"outbox appended {receipt}")
            if self.fault and not self.state["fault_triggered"]:
                self.state["fault_triggered"] = True
                self.event("fault.ack_lost", "commit happened; success acknowledgement lost")
                return {"ok": False, "error": "ack_lost", "message": "Outcome unknown."}
            self.event("tool.response", receipt)
            return {"ok": True, "receipt_id": receipt}

    async def _fetch(self) -> dict:
        self.state["pending"] += 1
        self.event("tool.started", "fetch_status")
        try:
            if self.fault:
                self.state["fault_triggered"] = True
                self.event("fault.hang", "provider will not complete")
                await asyncio.Event().wait()
            self.state["completed_reads"] += 1
            self.event("tool.response", "build complete")
            return {"ok": True, "status": "complete"}
        finally:
            self.state["pending"] -= 1
            self.event("tool.cleaned_up", "pending operation released")
