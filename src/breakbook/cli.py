"""Small CLI: reproduce, compare, inspect, and keep a regression test."""

import argparse
import asyncio
import sys
from pathlib import Path

from . import __version__
from .catalog import CASES
from .export import export_pytest
from .models import Limits
from .reports import load_report, save_bundle, save_html, save_junit
from .runner import make_report, run_trial


def parser():
    root = argparse.ArgumentParser(
        prog="breakbook", description="Executable agent failures and regression tests."
    )
    root.add_argument("--version", action="version", version=f"Agent Breakbook {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Show the three executable cases")
    demo = commands.add_parser("demo", help="Offline scripted broken/fixed comparison")
    demo.add_argument("case", nargs="?", choices=[*CASES, "all"], default="all")
    demo.add_argument(
        "--offline",
        action="store_true",
        help="Explicitly select the offline demo (also the default)",
    )
    demo.add_argument("--out", type=Path, default=Path("results/demo"))
    run = commands.add_parser("run", help="Evaluate contracts; a failing trial exits nonzero")
    run.add_argument("case", nargs="?", choices=[*CASES, "all"], default="all")
    run.add_argument(
        "--adapter", choices=["scripted", "scripted-mcp", "openai-agents"], default="scripted"
    )
    run.add_argument("--variant", choices=["broken", "fixed", "both"], default="fixed")
    run.add_argument("--runs", type=int, default=1)
    run.add_argument("--model", help="Explicit accessible model ID; required for openai-agents")
    run.add_argument("--no-fault", action="store_true", help="Healthy-service positive control")
    run.add_argument("--out", type=Path, default=Path("results/run"))
    for flag, kind in [
        ("tool-timeout", float),
        ("watchdog", float),
        ("max-tool-calls", int),
        ("retry-attempts", int),
        ("max-turns", int),
        ("max-output-tokens", int),
        ("token-budget", int),
    ]:
        run.add_argument(f"--{flag}", type=kind, default=None)
    report = commands.add_parser("report", help="Render recorded JSON without rerunning an agent")
    report.add_argument("input", type=Path)
    report.add_argument("--out", type=Path, default=Path("results/report.html"))
    report.add_argument("--junit", type=Path)
    export = commands.add_parser(
        "export", help="Export a pytest starter with a replaceable adapter"
    )
    export.add_argument("case", choices=CASES)
    export.add_argument("--format", choices=["pytest"], default="pytest")
    export.add_argument("--out", type=Path, required=True)
    return root


async def execute(args):
    demo = args.command == "demo"
    adapter = "scripted" if demo else args.adapter
    options = {}
    if adapter == "openai-agents":
        options.update(tool_timeout=1, watchdog=60)
    elif adapter == "scripted-mcp":
        options.update(tool_timeout=0.1, watchdog=2)
    if not demo:
        options.update(
            {
                field: getattr(args, field)
                for field in Limits.model_fields
                if getattr(args, field) is not None
            }
        )
        if not 1 <= args.runs <= 100:
            raise ValueError("--runs must be between 1 and 100")
        if args.model and adapter != "openai-agents":
            raise ValueError("--model is only used with --adapter openai-agents")
    limits = Limits(**options)
    cases = list(CASES) if args.case == "all" else [args.case]
    variants = ["broken", "fixed"] if demo or args.variant == "both" else [args.variant]
    print(
        "Evidence: scripted demonstration (no model called)."
        if adapter.startswith("scripted")
        else "Evidence: live model + local simulated MCP services. Provider charges may apply.",
        flush=True,
    )
    trials = []
    for case in cases:
        for variant in variants:
            for index in range(1, (1 if demo else args.runs) + 1):
                trial = await run_trial(
                    case,
                    variant,
                    adapter=adapter,
                    limits=limits,
                    fault=True if demo else not args.no_fault,
                    index=index,
                    model=None if demo else args.model,
                )
                trials.append(trial)
                failed = ", ".join(check.name for check in trial.checks if not check.passed)
                print(
                    f"{trial.verdict.upper():11} {case:12} {variant:6} #{index}  {failed}",
                    flush=True,
                )
                # Preserve completed trials even if a later trial is interrupted.
                save_bundle(make_report(trials, limits, None if demo else args.model), args.out)
    print(f"Reports: {args.out / 'report.html'} | results.json | junit.xml")
    if any(t.verdict == "infra_error" for t in trials):
        return 3
    if demo:
        matched = all(t.verdict == ("fail" if t.variant == "broken" else "pass") for t in trials)
        print(
            "Demo reproduced expected failures and fixes."
            if matched
            else "Unexpected demo result; inspect the report."
        )
        return 0 if matched else 1
    return 0 if all(t.verdict == "pass" for t in trials) else 1


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "list":
            for case, detail in CASES.items():
                print(f"{case:12} {detail['summary']}")
            return 0
        if args.command in {"run", "demo"}:
            return asyncio.run(execute(args))
        if args.command == "report":
            report = load_report(args.input)
            save_html(report, args.out)
            if args.junit:
                save_junit(report, args.junit)
            print(f"Rendered {len(report.trials)} recorded trials to {args.out}")
            return 0
        for path in export_pytest(args.case, args.out):
            print(path)
        return 0
    except (ValueError, OSError) as exc:
        print(f"breakbook: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "breakbook: interrupted; completed trials remain in the output directory",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
