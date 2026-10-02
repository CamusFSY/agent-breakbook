# Contributing

Good additions make a specific failure easier to reproduce, understand, and prevent. Start with a minimal case or a bug report. Please include dependency versions, the command, expected versus observed behavior, and a sanitized report. Never include credentials, private prompts, or production records.

## A case should include

1. A narrow, useful task and a deterministic failure mode.
2. A broken control and a concrete boundary fix; avoid secretly changing the business task.
3. An independent state assertion that cannot pass from success prose alone.
4. A healthy-service positive control and a test that rejects no-op/fake-success shortcuts.
5. Limits, cancellation/cleanup behavior, source attribution, and known limitations.
6. Accurate evidence labels. A test model is not live-provider evidence.

Add the implementation to `world.py`, contracts to `contracts.py`, metadata to `catalog.py`, and tests/guides alongside them. If a new case makes those modules unwieldy, propose a focused refactor with the case. We prefer a small useful library to an early plugin framework.

## Local validation

```bash
uv sync --locked --extra openai --group dev
uv run ruff format .
uv run ruff check .
uv run pytest -q
uv run breakbook demo --offline
uv build
```

The test suite does not need a provider API key. Describe exactly which checks you ran. If you ran a paid model, report the model ID, date, versions, limits, number of trials, raw sanitized records, and mixed outcomes. Do not generalize from three synthetic cases.

By contributing, you agree that your contributions are licensed under Apache-2.0. Respect source project licenses and credit ideas or incident reports. Be considerate in discussions and focus criticism on reproducible behavior.
