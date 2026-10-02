"""Export a small, runnable contract test with a replaceable agent callback."""

from pathlib import Path

from .catalog import CASES


def export_pytest(case: str, directory: Path) -> list[Path]:
    if case not in CASES:
        raise ValueError(f"Unknown case: {case}")
    test = f'''"""Generated regression test. Replace run_agent with your own async adapter.

The bundled callback is SCRIPTED. It does not evaluate a real language model.
"""

import asyncio

from breakbook.adapters.scripted import run_scripted
from breakbook.models import Limits
from breakbook.runner import run_trial


async def run_agent(case, variant, call, limits):
    # Route your agent's tools through await call(tool_name, arguments).
    # Return AdapterResult with an honest, structured Outcome.
    return await run_scripted(case, variant, call, limits)


def test_{case.replace("-", "_")}_contract():
    for fault in (True, False):
        trial = asyncio.run(run_trial(
            "{case}", "fixed", adapter="custom", custom_runner=run_agent,
            limits=Limits(watchdog=5), fault=fault,
        ))
        assert trial.verdict == "pass", [
            check.model_dump() for check in trial.checks if not check.passed
        ]
'''
    files = {
        f"test_{case.replace('-', '_')}.py": test,
        "requirements.txt": (
            "# Pin to the released Git tag; no PyPI publication is implied.\n"
            "agent-breakbook @ git+https://github.com/CamusFSY/agent-breakbook.git@v0.1.0\n"
            "pytest>=8,<10\n"
        ),
        "README.md": (
            f"# {case} regression starter\n\n"
            "Run `python -m pip install -r requirements.txt`, then `python -m pytest -q`.\n\n"
            "The included callback is a scripted example. Replace `run_agent` in the test "
            "with your adapter and route its tool calls through the supplied `call` function. "
            "Return `AdapterResult(outcome=Outcome(...))`; never bypass the fixture. "
            "Fault-on and fault-off controls both have to pass. The custom adapter label "
            "does not automatically claim live-model evidence.\n\n"
            "See the repository's docs/adapters.md for callback and tool contracts.\n"
        ),
    }
    for name in files:
        if (directory / name).exists():
            raise ValueError(f"Refusing to overwrite {directory / name}")
    directory.mkdir(parents=True, exist_ok=True)
    for name, contents in files.items():
        (directory / name).write_text(contents, encoding="utf-8")
    return [directory / name for name in files]
