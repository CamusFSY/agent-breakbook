"""The real Agents SDK drives a real MCP subprocess, with a fake model only."""

import json

import pytest

pytest.importorskip("agents")
from agents import Model, ModelResponse, Usage  # noqa: E402
from openai.types.responses import (  # noqa: E402
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from breakbook.models import Limits  # noqa: E402
from breakbook.runner import run_trial  # noqa: E402


class FixtureModel(Model):
    def __init__(self, case, tokens=10):
        self.case = case
        self.step = 0
        self.tokens = tokens
        self.inputs = []

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        **kwargs,
    ):
        assert tracing.is_disabled()
        assert model_settings.max_tokens is not None
        self.inputs.append(input)
        self.step += 1
        call_count = {"lost-ack": 2, "hung-tool": 1, "retry-storm": 4}[self.case]
        if self.step <= call_count:
            name = {
                "lost-ack": "send_notification",
                "hung-tool": "fetch_status",
                "retry-storm": "read_inventory",
            }[self.case]
            assert name in [tool.name for tool in tools]
            args = (
                {"operation_id": "build-42", "message": "Build finished"}
                if self.case == "lost-ack"
                else {}
            )
            output = ResponseFunctionToolCall(
                id=f"tool-{self.step}",
                call_id=f"call-{self.step}",
                type="function_call",
                name=name,
                arguments=json.dumps(args),
            )
        else:
            status = {"lost-ack": "sent", "hung-tool": "timed_out", "retry-storm": "unavailable"}[
                self.case
            ]
            answer = {
                "status": status,
                "receipt_id": "receipt-1" if self.case == "lost-ack" else None,
            }
            output = ResponseOutputMessage(
                id="final",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(type="output_text", text=json.dumps(answer), annotations=[])
                ],
            )
        return ModelResponse(
            output=[output],
            usage=Usage(
                requests=1,
                input_tokens=self.tokens,
                output_tokens=self.tokens,
                total_tokens=self.tokens * 2,
            ),
            response_id=None,
        )

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError("Streaming is not used by this adapter")


@pytest.mark.parametrize("case", ["lost-ack", "hung-tool", "retry-storm"])
async def test_actual_sdk_and_mcp_without_a_paid_provider(case, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    model = FixtureModel(case)
    trial = await run_trial(case, adapter="openai-agents", model=model, limits=Limits(watchdog=5))
    assert trial.verdict == "pass", trial.model_dump()
    assert trial.evidence == "sdk-test-model"
    assert trial.transport == "mcp-stdio"
    assert trial.result.usage["requests"] == model.step
    tool_results = [item for item in model.inputs[-1] if item.get("type") == "function_call_output"]
    assert tool_results, "Model must actually receive the MCP results"


async def test_sdk_token_budget():
    model = FixtureModel("lost-ack", tokens=300)
    trial = await run_trial(
        "lost-ack",
        adapter="openai-agents",
        model=model,
        limits=Limits(watchdog=5, token_budget=512),
    )
    assert trial.verdict == "fail", trial.model_dump()
    assert trial.result.termination == "token_budget"
    assert model.step == 1
    assert trial.result.usage["total_tokens"] == 600


async def test_sdk_turn_budget():
    trial = await run_trial(
        "lost-ack",
        adapter="openai-agents",
        model=FixtureModel("lost-ack"),
        limits=Limits(watchdog=5, max_turns=1),
    )
    assert trial.result.termination == "turn_budget", trial.model_dump()


async def test_sdk_watchdog_cleans_up_hung_mcp():
    trial = await run_trial(
        "hung-tool",
        "broken",
        adapter="openai-agents",
        model=FixtureModel("hung-tool"),
        limits=Limits(watchdog=1),
    )
    assert trial.result.termination == "watchdog", trial.model_dump()
    assert trial.state["pending"] == 0


async def test_live_adapter_requires_explicit_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await run_trial("lost-ack", adapter="openai-agents", model="explicit-model-id")
