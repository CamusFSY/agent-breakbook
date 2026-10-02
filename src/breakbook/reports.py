"""Portable reports with no remote assets, telemetry, or embedded tool execution."""

import html
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .catalog import CASES
from .contracts import verify
from .models import Report


def load_report(path: Path) -> Report:
    report = Report.model_validate_json(path.read_text(encoding="utf-8"))
    # Imported reports must agree with their recorded state, not only their verdict label.
    for trial in report.trials:
        try:
            checks = verify(trial.case, trial.state, trial.result, report.limits, trial.fault)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Incomplete state in imported report") from exc
        verdict = "pass" if all(c.passed for c in checks) else "fail"
        if trial.result.termination == "infra_error":
            verdict = "infra_error"
        if trial.checks != checks or trial.verdict != verdict:
            raise ValueError("Imported verdict/checks disagree with recorded state")
    return report


def save_json(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def save_junit(report: Report, path: Path) -> None:
    counts = report.summary()
    root = ET.Element(
        "testsuite",
        {
            "name": "agent-breakbook",
            "tests": str(counts["total"]),
            "failures": str(counts["fail"]),
            "errors": str(counts["infra_error"]),
            "time": f"{sum(t.duration_ms for t in report.trials) / 1000:.3f}",
        },
    )
    for trial in report.trials:
        test = ET.SubElement(
            root,
            "testcase",
            {
                "classname": f"breakbook.{trial.adapter}.{trial.case}",
                "name": f"{trial.variant}.fault-{trial.fault}.run-{trial.index}",
                "time": f"{trial.duration_ms / 1000:.3f}",
            },
        )
        properties = ET.SubElement(test, "properties")
        ET.SubElement(properties, "property", {"name": "evidence", "value": trial.evidence})
        failed = [
            f"{c.name}: expected {c.expected}; got {c.actual}" for c in trial.checks if not c.passed
        ]
        if trial.verdict == "infra_error":
            ET.SubElement(
                test, "error", {"message": trial.result.error or "Infrastructure error"}
            ).text = "\n".join(failed)
        elif trial.verdict == "fail":
            ET.SubElement(
                test,
                "failure",
                {"message": "; ".join(c.name for c in trial.checks if not c.passed)},
            ).text = "\n".join(failed)
        ET.SubElement(
            test, "system-out"
        ).text = f"evidence={trial.evidence}; termination={trial.result.termination}"
    ET.indent(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


STYLE = """
:root{color-scheme:dark;--bg:#101318;--panel:#191e26;--ink:#ecf0f7;--dim:#b0bccd;
--line:#354052;--green:#76e3bd;--red:#ff9fae;--blue:#9fc8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}
main{max-width:1120px;padding:48px 24px 72px;margin:auto}h1{font-size:clamp(32px,5vw,54px);line-height:1.1;margin:8px 0 18px;letter-spacing:-2px}
h2{font-size:22px;margin:0}h3{font-size:16px}.eyebrow{letter-spacing:3px;color:var(--green);font-size:12px;font-weight:700}
.muted,small{color:var(--dim)}.intro{max-width:780px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:30px 0}
.stat,.trial,.meta{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px}.stat strong{display:block;font-size:30px}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0}button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:8px 15px;cursor:pointer}
button[aria-pressed=true]{border-color:var(--green);color:var(--green)}button:focus-visible,summary:focus-visible{outline:2px solid var(--blue);outline-offset:4px}
.trial{margin:16px 0}.head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.badge{white-space:nowrap;border:1px solid currentColor;border-radius:5px;padding:2px 8px;font-size:12px;font-weight:700}
.pass{color:var(--green)}.fail{color:var(--red)}.infra_error{color:#f3c886}.tags{color:var(--dim);font:13px/1.7 ui-monospace,monospace;margin:8px 0 16px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}th{color:var(--dim);font-weight:500}
.scroll{overflow-x:auto}summary{cursor:pointer;color:var(--blue);padding:14px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg);padding:14px;border-radius:6px;font-size:12px}
.events{padding-left:26px;font:13px/1.8 ui-monospace,monospace}.events b{color:var(--blue)}footer{margin-top:36px;color:var(--dim);font-size:13px}a{color:var(--blue)}[hidden]{display:none!important}
@media(max-width:600px){main{padding:24px 14px}.stats{grid-template-columns:repeat(2,1fr)}.trial{padding:14px}.head{display:block}.head .badge{display:inline-block;margin-top:10px}th,td{padding:8px 4px}}
"""


def render_html(report: Report) -> str:
    esc = lambda value: html.escape(str(value), quote=True)  # noqa: E731
    counts = report.summary()
    stats = "".join(
        f'<div class="stat"><strong>{counts[k]}</strong>{label}</div>'
        for k, label in [
            ("total", "Trials"),
            ("pass", "Passed"),
            ("fail", "Failed contracts"),
            ("infra_error", "Infrastructure errors"),
        ]
    )
    trials = []
    for trial in report.trials:
        rows = "".join(
            f'<tr><td class="{"pass" if c.passed else "fail"}">{"PASS" if c.passed else "FAIL"}</td>'
            f"<td>{esc(c.name)}</td><td>{esc(c.expected)}</td><td>{esc(c.actual)}</td></tr>"
            for c in trial.checks
        )
        events = "".join(
            f"<li><b>{esc(e.get('kind', ''))}</b> — {esc(e.get('detail', ''))}</li>"
            for e in trial.state.get("events", [])
        )
        trials.append(f"""<article class="trial" data-verdict="{trial.verdict}">
<div class="head"><div><small>{esc(trial.case)} / run {trial.index}</small>
<h2>{esc(CASES[trial.case]["title"])}</h2></div><span class="badge {trial.verdict}">{trial.verdict.upper()}</span></div>
<p class="tags">{esc(trial.variant)} · {esc(trial.evidence)} · {esc(trial.transport)} · fault {"on" if trial.fault else "off"} · {trial.duration_ms:.1f} ms</p>
<p>{esc(CASES[trial.case]["mitigation"])}</p>
<div class="scroll"><table><thead><tr><th>Result</th><th>Contract</th><th>Expected</th><th>Observed</th></tr></thead><tbody>{rows}</tbody></table></div>
<details><summary>Inspect event timeline &amp; recorded result</summary><ol class="events">{events}</ol>
<pre>{esc(json.dumps(trial.result.model_dump(), indent=2))}</pre></details></article>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent Breakbook · Run report</title>
<style>{STYLE}</style></head><body><main><header><div class="eyebrow">AGENT BREAKBOOK / v{esc(report.breakbook_version)}</div>
<h1>Break it. Fix it. Keep the test.</h1><p class="intro muted">Local fault experiments with independent state checks.
<b>Scripted runs and SDK test models are demonstrations, not live model evaluations.</b>
A broken profile can pass when an agent recovers safely. A failed contract is evidence about this run only.</p></header>
<section class="stats" aria-label="Run summary">{stats}</section>
<details class="meta"><summary>Run metadata, evidence &amp; limits</summary><p>{esc(report.created_at)}</p>
<pre>{esc(json.dumps(report.environment, indent=2))}</pre><pre>{esc(report.limits.model_dump_json(indent=2))}</pre>
<p class="muted">Metadata is self-reported. This file is not a signed attestation. Live runs use real models against local simulated services.</p></details>
<nav class="controls" aria-label="Filter trials"><button data-filter="all" aria-pressed="true">All</button><button data-filter="pass" aria-pressed="false">Passed</button><button data-filter="fail" aria-pressed="false">Failed</button><button data-filter="infra_error" aria-pressed="false">Errors</button></nav>
<p id="visible-count" class="muted" aria-live="polite">Showing {counts["total"]} trials</p>
{"".join(trials)}<footer>Agent Breakbook · Apache-2.0 · No external assets or telemetry. Raw JSON is the portable record.</footer></main>
<script>document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{{
document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
let count=0;document.querySelectorAll('[data-verdict]').forEach(card=>{{card.hidden=button.dataset.filter!=='all'&&card.dataset.verdict!==button.dataset.filter;if(!card.hidden)count++;}});
document.getElementById('visible-count').textContent='Showing '+count+' trials';
}}));</script></body></html>"""


def save_html(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")


def save_bundle(report: Report, directory: Path) -> None:
    save_json(report, directory / "results.json")
    save_html(report, directory / "report.html")
    save_junit(report, directory / "junit.xml")
