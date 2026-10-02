# Case guide

All three cases use synthetic local state and make no external service calls. `src/breakbook/world.py` implements the service boundaries; `contracts.py` evaluates their state. The scripted client lives in `adapters/scripted.py`.

## lost-ack: a failed response does not mean a failed write

1. The client calls `send_notification` with operation ID `build-42` and message `Build finished`.
2. The service appends a notification, then returns `ack_lost` rather than a receipt.
3. The same client retries using the same business ID.
4. The broken service appends a second notification. The fixed service returns the original receipt.

The fixed boundary atomically checks the key and commits under one lock. It rejects reuse of a key with a different payload. The independent contract checks the number of commits, the exact business payload, and the returned receipt. Merely reporting “sent” cannot pass.

`lookup_notification` is also available over MCP. The live adapter instructs the model to look up ambiguous writes before retrying, so a model can pass on the broken service too. The scripted demonstration deliberately retries the same call to exercise server-side deduplication.

**Healthy control:** the initial send succeeds, one notification is stored, and its receipt is returned. Separate tests verify different operation IDs remain usable and concurrent same-ID requests do not duplicate writes.

**Limits:** this is an application-level ambiguous error after commit, not real network packet loss. The in-memory lock only coordinates one process. A production implementation needs durable keys, atomic database constraints/transactions, retention policy, and a strategy for downstream side effects. This fixture is not an exactly-once guarantee across restarts.

**Provenance:** original implementation of a well-known distributed-systems pattern. [FaultBench](https://github.com/mit-hun-k/faultbench) is closely related stateful fault-injection work. No production incident reproduction or algorithmic novelty is claimed.

## hung-tool: the last safety net is not the fix

`fetch_status` starts a pending operation that waits forever when the fault is enabled. The broken boundary has no application deadline. The harness eventually cancels the run and records `watchdog`; the contract fails even when cleanup succeeds.

The fixed boundary uses `asyncio.timeout(tool_timeout)`, releases the pending operation in `finally`, and returns `tool_timeout`. The client must return `timed_out`. Contracts require an application deadline event, no remaining pending work, and an honest outcome.

**Healthy control:** the read returns normally, emits no deadline event, and produces status `ok`.

**Limits:** this tests cooperative async cancellation inside a local fixture. It does not prove cleanup of blocking native calls, remote background jobs, or arbitrary external processes. MCP startup/handshake and teardown have their own transport timeouts and are outside the per-agent watchdog.

**Provenance:** inspired by reports of hanging tool calls, including [MCP Python SDK issue #1401](https://github.com/modelcontextprotocol/python-sdk/issues/1401). This simulation does not claim that the pinned current SDK contains that issue.

## retry-storm: place the budget outside the model

`read_inventory` always returns `rate_limit` with the fault on. The same scripted client keeps retrying until it sees a boundary stop signal. The broken service permits attempts until the harness ceiling is reached. The fixed service permits at most `retry_attempts` provider attempts, then returns `retry_limit` without touching the provider again.

The default fixed run performs three provider attempts and a fourth tool call that receives the stop signal. The contract checks the provider-attempt count, that the outer harness was not needed, and that the client reports `unavailable`.

**Healthy control:** inventory is returned on the first request and the client reports `ok`.

**Limits:** the tiny fixture enforces an attempt cap; it does not implement waiting, exponential backoff, jitter, a sliding-window quota, or a resetting circuit breaker. `retry_after_ms` is illustrative. A model can choose to stop earlier than the service budget and still pass.

**Provenance:** original synthetic case of a known failure mode. [Agentic Chaos](https://github.com/DeepAgentLabs/agentic-chaos) is related work in agent fault injection.

## Interpreting comparisons

Run both fault-on and fault-off controls. A no-op agent, a fake success response, or a service that refuses all useful work is not a valid fix. The tests explicitly exercise these shortcuts. Do not combine scripted demonstrations and live runs into a single model success-rate claim. Repeated deterministic runs check consistency, not statistical generalization.
