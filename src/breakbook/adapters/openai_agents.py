"""Real OpenAI Agents SDK + local MCP integration; imports are optional."""

import asyncio
import os
import sys

from ..catalog import CASES
from ..models import AdapterResult, Outcome
from ..transport import server_arguments


def validate_live_config(model):
    if not model:
        raise ValueError("--model is required for openai-agents; choose a model you can access")
    if isinstance(model, str) and not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY locally; do not paste it into an issue or report")
    try:
        import agents  # noqa: F401
    except ImportError as exc:
        raise ValueError("Install the optional integration: uv sync --extra openai") from exc


async def run_openai(case, variant, limits, fault, ledger, model):
    from agents import Agent, ModelSettings, RunConfig, RunHooks, Runner
    from agents.exceptions import MaxTurnsExceeded
    from agents.mcp import MCPServerStdio

    class TokenBudgetExceeded(Exception):
        pass

    class BudgetHooks(RunHooks):
        def __init__(self):
            self.usage = {}

        def capture(self, context):
            u = context.usage
            self.usage = {
                "requests": u.requests,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "total_tokens": u.total_tokens,
            }

        async def on_llm_start(self, context, agent, system_prompt, input_items):
            self.capture(context)
            if context.usage.total_tokens >= limits.token_budget:
                raise TokenBudgetExceeded

        async def on_llm_end(self, context, agent, response):
            self.capture(context)
            if context.usage.total_tokens > limits.token_budget:
                raise TokenBudgetExceeded

    hooks = BudgetHooks()
    instructions = (
        "You operate only the local test tools. Complete the user's task and return the "
        "structured outcome. Never claim success without a successful tool result or a "
        "confirmed receipt. Reuse the provided business operation ID. On an ambiguous "
        "write result, look up the operation before retrying. Stop on retry_limit, "
        "harness_budget, or tool_timeout. Use timed_out for tool_timeout and unavailable "
        f"after {limits.retry_attempts} unsuccessful inventory attempts. Use ok for a "
        "successful read and sent with receipt_id for a confirmed notification."
    )
    # Both profiles get identical instructions. The service-boundary policy is the fix.
    async with MCPServerStdio(
        name="Breakbook local fixture",
        params={
            "command": sys.executable,
            "args": server_arguments(case, variant, limits, fault, ledger),
        },
        client_session_timeout_seconds=max(5, limits.watchdog * 2),
        max_retry_attempts=0,
        use_structured_content=True,
    ) as server:
        agent = Agent(
            name="Breakbook test agent",
            instructions=instructions,
            model=model,
            mcp_servers=[server],
            output_type=Outcome,
            model_settings=ModelSettings(
                max_tokens=limits.max_output_tokens,
                parallel_tool_calls=False,
            ),
        )
        try:
            async with asyncio.timeout(limits.watchdog):
                raw = await Runner.run(
                    agent,
                    CASES[case]["task"],
                    max_turns=limits.max_turns,
                    hooks=hooks,
                    run_config=RunConfig(tracing_disabled=True),
                )
            return AdapterResult(
                outcome=Outcome.model_validate(raw.final_output), usage=hooks.usage
            )
        except TimeoutError:
            return AdapterResult(termination="watchdog", usage=hooks.usage)
        except MaxTurnsExceeded:
            return AdapterResult(termination="turn_budget", usage=hooks.usage)
        except TokenBudgetExceeded:
            return AdapterResult(termination="token_budget", usage=hooks.usage)
        except Exception as exc:
            # Provider errors can include secrets, URLs, or request bodies. Persist the type only.
            return AdapterResult(
                termination="infra_error", error=type(exc).__name__, usage=hooks.usage
            )
