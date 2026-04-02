from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from course_management_system import build_demo_system  # noqa: E402


SCRIPT_DIR = Path(__file__).resolve().parent
ATHERIS_DIR = SCRIPT_DIR.parent
RAW_DIR = ATHERIS_DIR / "raw"
RESULTS_DIR = ATHERIS_DIR / "results"
CORPUS_DIR = RAW_DIR / "corpus"
CRASH_DIR = RAW_DIR / "crashes"
FUZZER_SCRIPT = SCRIPT_DIR / "fuzz_course_management_atheris.py"
LOG_FILE = RAW_DIR / "atheris.log"
COVERAGE_DATA = RAW_DIR / ".coverage"
COVERAGE_JSON = RAW_DIR / "coverage.json"
JSON_FILE = RESULTS_DIR / "atheris_summary.json"
MD_FILE = RESULTS_DIR / "atheris_summary.md"
RUN_COUNT = 50000
MAX_LEN = 256
SEED_PREFIXES = {
    "seed_parse_time.bin": b"\x00\x00" + b"09:30",
    "seed_parse_meeting.bin": b"\x01\x00" + b"Mon 09:00-10:15",
    "seed_conflict.bin": b"\x02\x00" + b"Mon 09:00-10:00",
    "seed_serialize.bin": b"\x03\x00" + b"serialize",
    "seed_registration.bin": b"\x05\x00" + b"SEC1001:S001",
    "seed_bytes.bin": b"\x05\x00\xff\x00Mon\x00Wed\x00SEC1004",
}


def parse_coverage_percent(coverage_json_path: Path, target_suffix: str) -> float | None:
    if not coverage_json_path.exists():
        return None

    data = json.loads(coverage_json_path.read_text(encoding="utf-8"))
    for file_path, file_data in data.get("files", {}).items():
        if file_path.endswith(target_suffix):
            return float(file_data["summary"]["percent_covered"])
    return None


def collect_crash_files() -> list[str]:
    if not CRASH_DIR.exists():
        return []
    return sorted(path.name for path in CRASH_DIR.iterdir() if path.is_file())


def collect_corpus_files() -> list[str]:
    if not CORPUS_DIR.exists():
        return []
    return sorted(path.name for path in CORPUS_DIR.iterdir() if path.is_file())


def reset_directory_contents(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def seed_corpus() -> None:
    for name, data in SEED_PREFIXES.items():
        (CORPUS_DIR / name).write_bytes(data)
    system_payload = json.dumps(build_demo_system().to_dict()).encode("utf-8")
    (CORPUS_DIR / "seed_valid_system_json.bin").write_bytes(b"\x04\x00" + system_payload)
    (CORPUS_DIR / "seed_empty_system_json.bin").write_bytes(
        b"\x04\x00" + json.dumps({}).encode("utf-8")
    )
    (CORPUS_DIR / "seed_partial_schema_json.bin").write_bytes(
        b"\x04\x00" + json.dumps({"students": {"S1": {}}}).encode("utf-8")
    )


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    reset_directory_contents(CORPUS_DIR)
    reset_directory_contents(CRASH_DIR)
    seed_corpus()

    environment = os.environ.copy()
    environment["COVERAGE_FILE"] = str(COVERAGE_DATA)

    command = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        str(FUZZER_SCRIPT),
        str(CORPUS_DIR),
        f"-atheris_runs={RUN_COUNT}",
        f"-max_len={MAX_LEN}",
        f"-artifact_prefix={CRASH_DIR}{os.sep}",
    ]

    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True, env=environment)
    duration_seconds = round(time.perf_counter() - start_time, 3)

    combined_output = completed.stdout
    if completed.stderr:
        combined_output = f"{combined_output}\n[stderr]\n{completed.stderr}"
    LOG_FILE.write_text(combined_output, encoding="utf-8")

    coverage_command = [
        sys.executable,
        "-m",
        "coverage",
        "json",
        "-o",
        str(COVERAGE_JSON),
        "--include=*/course_management_system.py",
    ]
    coverage_completed = subprocess.run(
        coverage_command,
        capture_output=True,
        text=True,
        env=environment,
    )

    crash_files = collect_crash_files()
    corpus_files = collect_corpus_files()
    coverage_percent = parse_coverage_percent(COVERAGE_JSON, "course_management_system.py")

    summary = {
        "tool": "Atheris",
        "started_at_utc": started_at,
        "duration_seconds": duration_seconds,
        "exit_code": completed.returncode,
        "coverage_exit_code": coverage_completed.returncode,
        "run_count": RUN_COUNT,
        "max_len": MAX_LEN,
        "fuzzer_script": str(FUZZER_SCRIPT),
        "raw_log": str(LOG_FILE),
        "corpus_dir": str(CORPUS_DIR),
        "crash_dir": str(CRASH_DIR),
        "coverage_json": str(COVERAGE_JSON),
        "course_management_system_percent_covered": coverage_percent,
        "corpus_files": corpus_files,
        "crash_files": crash_files,
    }
    JSON_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Atheris Results",
        "",
        f"- Started at (UTC): `{started_at}`",
        f"- Duration (seconds): `{duration_seconds}`",
        f"- Exit code: `{completed.returncode}`",
        f"- Coverage export exit code: `{coverage_completed.returncode}`",
        f"- Fuzzer script: `{FUZZER_SCRIPT}`",
        f"- Run count: `{RUN_COUNT}`",
        f"- Max input length: `{MAX_LEN}`",
        f"- Raw log: `{LOG_FILE}`",
        f"- Corpus directory: `{CORPUS_DIR}`",
        f"- Crash directory: `{CRASH_DIR}`",
        f"- Coverage JSON: `{COVERAGE_JSON}`",
        f"- Corpus files: `{len(corpus_files)}`",
        f"- Crash artifacts: `{len(crash_files)}`",
    ]

    if coverage_percent is None:
        lines.append("- `course_management_system.py` coverage: unavailable")
    else:
        lines.append(f"- `course_management_system.py` coverage: `{coverage_percent:.2f}%`")

    lines.extend(
        [
            "",
            "## Crash Files",
            "",
        ]
    )
    if crash_files:
        lines.extend(f"- `{name}`" for name in crash_files)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Raw Log Tail",
            "",
            "```text",
            "\n".join(LOG_FILE.read_text(encoding="utf-8").splitlines()[-40:]),
            "```",
        ]
    )

    MD_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
