import json
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from breakbook.cli import main
from breakbook.export import export_pytest
from breakbook.models import Limits
from breakbook.reports import load_report, render_html, save_json, save_junit
from breakbook.runner import make_report, run_trial


def test_demo_and_report_commands(tmp_path):
    assert main(["demo", "--offline", "--out", str(tmp_path)]) == 0
    report = load_report(tmp_path / "results.json")
    assert report.summary() == {"total": 6, "pass": 3, "fail": 3, "infra_error": 0}
    assert (
        main(
            [
                "report",
                str(tmp_path / "results.json"),
                "--out",
                str(tmp_path / "copy.html"),
                "--junit",
                str(tmp_path / "copy.xml"),
            ]
        )
        == 0
    )
    assert (tmp_path / "copy.html").read_text() == (tmp_path / "report.html").read_text()
    junit = ET.parse(tmp_path / "copy.xml").getroot()
    assert junit.attrib["tests"] == "6" and junit.attrib["failures"] == "3"


def test_run_exit_codes_and_positive_control(tmp_path, monkeypatch):
    common = ["--out", str(tmp_path)]
    assert main(["run", "lost-ack", "--variant", "broken", *common]) == 1
    assert main(["run", "lost-ack", "--variant", "broken", "--no-fault", *common]) == 0
    assert main(["run", "--runs", "0", *common]) == 2
    assert main(["run", "--tool-timeout", "2", "--watchdog", "1", *common]) == 2
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["run", "--adapter", "openai-agents", "--model", "test", *common]) == 2


async def test_html_escapes_all_untrusted_text(tmp_path):
    trial = await run_trial("lost-ack")
    attack = '</pre><script>alert("oops")</script>'
    trial.state["events"].append({"seq": 999, "kind": attack, "detail": attack})
    trial.result.error = attack
    report = make_report([trial], Limits(), attack)
    rendered = render_html(report)
    assert attack not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script src=" not in rendered
    path = tmp_path / "junit.xml"
    save_junit(report, path)
    assert ET.parse(path).getroot().attrib["tests"] == "1"


async def test_import_rejects_forged_verdict(tmp_path):
    trial = await run_trial("lost-ack", "broken")
    path = tmp_path / "results.json"
    save_json(make_report([trial], Limits()), path)
    data = json.loads(path.read_text())
    data["trials"][0]["verdict"] = "pass"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="disagree"):
        load_report(path)


async def test_junit_distinguishes_infrastructure_error(tmp_path):
    async def crashed(*args):
        raise RuntimeError

    trial = await run_trial("lost-ack", adapter="custom", custom_runner=crashed)
    path = tmp_path / "junit.xml"
    save_junit(make_report([trial], Limits()), path)
    root = ET.parse(path).getroot()
    assert root.attrib["errors"] == "1" and root.attrib["failures"] == "0"
    assert root.find("testcase/error") is not None


@pytest.mark.parametrize("case", ["lost-ack", "hung-tool", "retry-storm"])
def test_exported_tests_really_execute(case, tmp_path):
    files = export_pytest(case, tmp_path)
    assert len(files) == 3
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", str(files[0])],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with pytest.raises(ValueError, match="overwrite"):
        export_pytest(case, tmp_path)


def test_console_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "breakbook.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0 and "0.1.0" in result.stdout
