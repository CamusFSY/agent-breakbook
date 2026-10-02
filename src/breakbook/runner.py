"""Run bounded experiments and verify state outside the tested adapter."""

import asyncio
import importlib.metadata
import json
import platform
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .adapters.scripted import run_scripted
from .catalog import CASES
from .contracts import verify
from .models import AdapterResult, Limits, Report, Trial
from .transport import mcp_call
from .world import World


async def bounded(script: Awaitable[AdapterResult], limits: Limits) -> AdapterResult:
    try:
        async with asyncio.timeout(limits.watchdog):
            return await script
    except TimeoutError:
        return AdapterResult(termination="watchdog")


async def run_trial(
    case,
    variant="fixed",
    *,
    adapter="scripted",
    limits=None,
    fault=True,
    index=1,
    model=None,
    custom_runner: Callable | None = None,
) -> Trial:
    limits = limits or Limits()
    if case not in CASES or variant not in {"broken", "fixed"}:
        raise ValueError("Unknown case or variant")
    if adapter == "custom" and custom_runner is None:
        raise ValueError("custom_runner is required for the custom adapter")
    if adapter == "openai-agents":
        from .adapters.openai_agents import validate_live_config

        validate_live_config(model)
    if adapter not in {"scripted", "scripted-mcp", "openai-agents", "custom"}:
        raise ValueError(f"Unknown adapter: {adapter}")
    started = time.monotonic()
    world = World(case, variant, limits, fault=fault)
    state = world.snapshot()
    result = AdapterResult()
    transport = "in-process"
    try:
        if adapter in {"scripted", "custom"}:
            script = custom_runner or run_scripted
            result = await bounded(script(case, variant, world.call, limits), limits)
            state = world.snapshot()
        else:
            transport = "mcp-stdio"
            with tempfile.TemporaryDirectory(prefix="breakbook-") as directory:
                ledger = Path(directory) / "ledger.json"
                try:
                    if adapter == "scripted-mcp":
                        async with mcp_call(case, variant, limits, fault, ledger) as call:
                            result = await bounded(
                                run_scripted(case, variant, call, limits), limits
                            )
                    else:
                        from .adapters.openai_agents import run_openai

                        result = await run_openai(case, variant, limits, fault, ledger, model)
                finally:
                    if ledger.exists():
                        state = json.loads(ledger.read_text(encoding="utf-8"))
                if not ledger.exists():
                    raise RuntimeError("MCP server produced no ledger")
    except Exception as exc:
        if transport == "in-process":
            state = world.snapshot()
        result = AdapterResult(termination="infra_error", error=type(exc).__name__)
    checks = verify(case, state, result, limits, fault)
    verdict = "pass" if all(c.passed for c in checks) else "fail"
    if result.termination == "infra_error":
        verdict = "infra_error"
    evidence = "custom-adapter" if adapter == "custom" else "scripted"
    if adapter == "openai-agents":
        evidence = "live-model" if isinstance(model, str) else "sdk-test-model"
    # Custom adapters are deliberately not automatically classified as a live model.
    return Trial(
        case=case,
        variant=variant,
        adapter=adapter,
        transport=transport,
        evidence=evidence,
        index=index,
        fault=fault,
        verdict=verdict,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        result=result,
        checks=checks,
        state=state,
    )


def make_report(trials, limits, model=None):
    environment = {"python": platform.python_version(), "platform": platform.system()}
    for package in ["mcp", "openai-agents", "openai", "pydantic"]:
        try:
            environment[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    if isinstance(model, str):
        environment["model"] = model
    elif model is not None:
        environment["model"] = "test-double (no provider called)"
    return Report(
        breakbook_version=__version__,
        created_at=datetime.now(UTC).isoformat(),
        environment=environment,
        limits=limits,
        trials=trials,
    )
