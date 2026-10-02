# Bring your own agent

Export a starter and run it once before replacing its callback:

```bash
uv run breakbook export hung-tool --format pytest --out exported/hung-tool
uv run pytest exported/hung-tool
```

The generated `requirements.txt` installs the v0.1.0 Git tag, not a nonexistent PyPI release. Existing files are never overwritten by `export`.

## Callback interface

```python
from breakbook.models import AdapterResult, Outcome


async def run_agent(case, variant, call, limits):
    result = await call("fetch_status", {})
    return AdapterResult(outcome=Outcome(status="ok" if result["ok"] else "timed_out"))
```

This example is a deterministic callback for `hung-tool`, not an LLM. To test an agent, expose the supplied `call(name, arguments)` to that agent's tool execution path, await the agent, and translate its actual final output to `AdapterResult`. Do not manufacture success or use an unrelated service instead of the injected fixture. Use `adapter="custom", custom_runner=run_agent` with `run_trial`.

Callback arguments:

- `case`: `lost-ack`, `hung-tool`, or `retry-storm`.
- `variant`: the selected service profile. Prefer the same client policy for both profiles.
- `call`: async function returning the structured reply of a fixture tool.
- `limits`: validated `Limits`. Choose enough time for your actual agent, and honor cancellation.

Outcomes have `status` (`sent`, `ok`, `timed_out`, `unavailable`, `unknown`) and optional `receipt_id`. `sent` requires the real committed receipt. Successful Python completion alone does not imply a passed contract. For a non-completing adapter, return a non-`completed` termination if you capture the interruption yourself; otherwise let the harness cancel it.

## Available tools

| Case | Tool | Arguments | Useful responses |
| --- | --- | --- | --- |
| lost-ack | `send_notification` | `operation_id`, `message` | `receipt_id`, `ack_lost`, `idempotency_conflict` |
| lost-ack | `lookup_notification` | `operation_id` | `receipt_id` or null |
| hung-tool | `fetch_status` | `{}` | status or `tool_timeout` |
| retry-storm | `read_inventory` | `{}` | available quantity, `rate_limit`, `retry_limit` |

Replies use `{"ok": true, ...}` or `{"ok": false, "error": "..."}`. Every tool can return `harness_budget` when the experiment's execution ceiling is exceeded. For notification tests use exactly `build-42` and `Build finished`; the contract checks this business task rather than accepting any unrelated write.

## Evaluating the callback

```python
import asyncio
from breakbook.models import Limits
from breakbook.runner import run_trial

# run_agent is your callback from above.
trial = asyncio.run(
    run_trial(
        "hung-tool",
        "fixed",
        adapter="custom",
        custom_runner=run_agent,
        limits=Limits(tool_timeout=1, watchdog=60),
    )
)
assert trial.verdict == "pass", [c for c in trial.checks if not c.passed]
```

Also run with `fault=False`; refusing all work should not pass. Label custom runs with their actual provenance in accompanying notes. `custom-adapter` is deliberately not automatically relabeled as `live-model`.

For an existing MCP-capable integration, use `transport.mcp_call` to obtain the same callable over stdio, or follow the small optional adapter in `adapters/openai_agents.py`. v0.1.0 does not provide a generic attach-to-arbitrary-server command. A PR for a new adapter should test real framework behavior with an honest test double and document any unverified paid-provider path.
