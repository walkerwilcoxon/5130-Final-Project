from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


SCRIPT_DIR = Path(__file__).resolve().parent
HYPOTHESIS_DIR = SCRIPT_DIR.parent
RAW_DIR = HYPOTHESIS_DIR / "raw"
RESULTS_DIR = HYPOTHESIS_DIR / "results"
TEST_FILE = SCRIPT_DIR / "test_course_management_hypothesis.py"
LOG_FILE = RAW_DIR / "pytest_hypothesis.log"
JUNIT_FILE = RAW_DIR / "pytest_hypothesis.junit.xml"
JSON_FILE = RESULTS_DIR / "hypothesis_summary.json"
MD_FILE = RESULTS_DIR / "hypothesis_summary.md"


def extract_hypothesis_statistics(log_text: str) -> str:
    marker = "Hypothesis Statistics"
    if marker not in log_text:
        return ""
    start = log_text.index(marker)
    return log_text[start:].strip()


def parse_junit_counts(xml_path: Path) -> dict[str, int]:
    if not xml_path.exists():
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}

    root = ET.parse(xml_path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}

    return {
        "tests": int(suite.attrib.get("tests", 0)),
        "failures": int(suite.attrib.get("failures", 0)),
        "errors": int(suite.attrib.get("errors", 0)),
        "skipped": int(suite.attrib.get("skipped", 0)),
    }


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "pytest",
        str(TEST_FILE),
        "-q",
        "--hypothesis-show-statistics",
        f"--junitxml={JUNIT_FILE}",
    ]

    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True)
    duration_seconds = round(time.perf_counter() - start_time, 3)

    combined_output = completed.stdout
    if completed.stderr:
        combined_output = f"{combined_output}\n[stderr]\n{completed.stderr}"
    LOG_FILE.write_text(combined_output, encoding="utf-8")

    junit_counts = parse_junit_counts(JUNIT_FILE)
    hypothesis_statistics = extract_hypothesis_statistics(combined_output)

    summary = {
        "tool": "Hypothesis",
        "runner": "pytest",
        "started_at_utc": started_at,
        "duration_seconds": duration_seconds,
        "exit_code": completed.returncode,
        "test_file": str(TEST_FILE),
        "raw_log": str(LOG_FILE),
        "junit_xml": str(JUNIT_FILE),
        "counts": junit_counts,
        "hypothesis_statistics": hypothesis_statistics,
    }
    JSON_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Hypothesis Results",
        "",
        f"- Started at (UTC): `{started_at}`",
        f"- Duration (seconds): `{duration_seconds}`",
        f"- Exit code: `{completed.returncode}`",
        f"- Test file: `{TEST_FILE}`",
        f"- Raw log: `{LOG_FILE}`",
        f"- JUnit XML: `{JUNIT_FILE}`",
        f"- Tests: `{junit_counts['tests']}`",
        f"- Failures: `{junit_counts['failures']}`",
        f"- Errors: `{junit_counts['errors']}`",
        f"- Skipped: `{junit_counts['skipped']}`",
        "",
        "## Hypothesis Statistics",
        "",
    ]
    if hypothesis_statistics:
        lines.extend(["```text", hypothesis_statistics, "```"])
    else:
        lines.append("No Hypothesis statistics block was captured in the raw log.")

    MD_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
