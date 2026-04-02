from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
CROSSHAIR_DIR = SCRIPT_DIR.parent
RAW_DIR = CROSSHAIR_DIR / "raw"
RESULTS_DIR = CROSSHAIR_DIR / "results"
PROPERTIES_FILE = SCRIPT_DIR / "crosshair_properties.py"
LOG_FILE = RAW_DIR / "crosshair_check.log"
JSON_FILE = RESULTS_DIR / "crosshair_summary.json"
MD_FILE = RESULTS_DIR / "crosshair_summary.md"
PER_PATH_TIMEOUT = 1.5
PER_CONDITION_TIMEOUT = 12.0
MAX_UNINTERESTING_ITERATIONS = 20
ANALYSIS_KIND = "PEP316"


def parse_findings(output: str) -> list[str]:
    findings: list[str] = []
    for line in output.splitlines():
        if ": error:" in line:
            findings.append(line)
    return findings


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "crosshair",
        "check",
        str(PROPERTIES_FILE),
        f"--analysis_kind={ANALYSIS_KIND}",
        f"--per_path_timeout={PER_PATH_TIMEOUT}",
        f"--per_condition_timeout={PER_CONDITION_TIMEOUT}",
        f"--max_uninteresting_iterations={MAX_UNINTERESTING_ITERATIONS}",
    ]

    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True)
    duration_seconds = round(time.perf_counter() - start_time, 3)

    combined_output = completed.stdout
    if completed.stderr:
        combined_output = f"{combined_output}\n[stderr]\n{completed.stderr}"
    LOG_FILE.write_text(combined_output, encoding="utf-8")

    findings = parse_findings(combined_output)
    summary = {
        "tool": "CrossHair",
        "started_at_utc": started_at,
        "duration_seconds": duration_seconds,
        "exit_code": completed.returncode,
        "analysis_kind": ANALYSIS_KIND,
        "per_path_timeout": PER_PATH_TIMEOUT,
        "per_condition_timeout": PER_CONDITION_TIMEOUT,
        "max_uninteresting_iterations": MAX_UNINTERESTING_ITERATIONS,
        "properties_file": str(PROPERTIES_FILE),
        "raw_log": str(LOG_FILE),
        "finding_count": len(findings),
        "findings": findings,
    }
    JSON_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# CrossHair Results",
        "",
        f"- Started at (UTC): `{started_at}`",
        f"- Duration (seconds): `{duration_seconds}`",
        f"- Exit code: `{completed.returncode}`",
        f"- Analysis kind: `{ANALYSIS_KIND}`",
        f"- Per-path timeout: `{PER_PATH_TIMEOUT}`",
        f"- Per-condition timeout: `{PER_CONDITION_TIMEOUT}`",
        f"- Max uninteresting iterations: `{MAX_UNINTERESTING_ITERATIONS}`",
        f"- Properties file: `{PROPERTIES_FILE}`",
        f"- Raw log: `{LOG_FILE}`",
        f"- Findings: `{len(findings)}`",
        "",
        "## Findings",
        "",
    ]
    if findings:
        lines.extend(f"- `{finding}`" for finding in findings)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Raw Output",
            "",
            "```text",
            combined_output.strip(),
            "```",
        ]
    )

    MD_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
