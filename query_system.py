"""
query_system.py
----------------
Run parameterised CodeQL queries against a CodeQL database named "codeql-db".

Usage examples (Windows):
  python query_system.py calls-made  --function my_func
  python query_system.py callers-of  --function my_func
  python query_system.py variables   --function my_func
  python query_system.py branches    --function my_func

The database is always "codeql-db" in the current directory.
The CodeQL CLI executable is always "codeql" (must be on PATH).
Library dependencies are resolved automatically via qlpack.yml.
Output is JSON written to stdout.
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
QUERIES_DIR = SCRIPT_DIR / "queries"
DB_PATH = "codeql-db"


def _resolve_codeql_exe() -> str:
    """Resolve the CodeQL executable path.

    Some environments (IDE kernels, subprocesses) may not inherit shell PATH
    entries such as /opt/homebrew/bin on macOS. We therefore try PATH first,
    then common absolute locations.
    """
    found = shutil.which("codeql")
    if found:
        return found

    candidates = [
        "/opt/homebrew/bin/codeql",  # Apple Silicon Homebrew
        "/usr/local/bin/codeql",     # Intel Homebrew
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    return "codeql"


CODEQL_EXE = _resolve_codeql_exe()


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render_template(template_name: str, context: dict) -> str:
    """Render a Jinja2 .ql.j2 template and return the CodeQL source string."""
    env = Environment(
        loader=FileSystemLoader(str(QUERIES_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )
    return env.get_template(template_name).render(**context)


# ---------------------------------------------------------------------------
# CodeQL execution
# ---------------------------------------------------------------------------

def run_codeql_query(ql_source: str) -> list[dict]:
    """
    Write *ql_source* into the queries directory as a temp .ql file so that
    CodeQL resolves it within the qlpack (and therefore finds codeql/python-all
    via the pack cache). Executes the query, decodes to CSV, returns results.
        [{"location": "file.py:10:5", "message": "..."}, ...]
    """
    db_path = Path(DB_PATH).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"CodeQL database not found: {db_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # Write the .ql file inside the queries directory so CodeQL picks up
        # the qlpack.yml that sits one level above it.
        ql_file = QUERIES_DIR / "_tmp_query.ql"
        bqrs_file = tmpdir / "results.bqrs"
        csv_file = tmpdir / "results.csv"

        try:
            ql_file.write_text(ql_source, encoding="utf-8")

            # ---- compile + run --------------------------------------------
            _run_subprocess(
                [CODEQL_EXE, "query", "run",
                 "--database", str(db_path),
                 "--output", str(bqrs_file),
                 str(ql_file)],
                "CodeQL query execution",
            )
        finally:
            # Always clean up the temp .ql file
            if ql_file.exists():
                ql_file.unlink()

        # ---- decode bqrs -> CSV -------------------------------------------
        _run_subprocess(
            [CODEQL_EXE, "bqrs", "decode",
             "--format", "csv",
             "--output", str(csv_file),
             str(bqrs_file)],
            "BQRS decode",
        )

        return _parse_csv(csv_file)


def _parse_csv(csv_file) -> list[dict]:
    """Parse a CodeQL CSV result file into a list of dicts.

    Each row contains all columns from the select clause.
    Returns raw rows as dicts with col0, col1, ... keys so callers
    can decide how to interpret the columns.
    """
    rows = []
    with open(csv_file, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        headers = next(reader, None)
        for row in reader:
            if not row:
                continue
            rows.append({f"col{i}": v for i, v in enumerate(row)})
    return rows


def _run_subprocess(cmd: list[str], label: str) -> None:
    """Run a subprocess, raising RuntimeError with stderr on failure."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed (exit {result.returncode}):\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Individual query functions
# ---------------------------------------------------------------------------

def _unique(values: list[str]) -> list[str]:
    """Return deduplicated list preserving order."""
    seen = set()
    out = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def query_calls_made(function_name: str) -> list[str]:
    """Return the names of all functions that *function_name* calls."""
    ql = render_template("calls_made.ql.j2", {"caller_name": function_name})
    rows = run_codeql_query(ql)
    return _unique([r["col1"] for r in rows if "col1" in r])


def query_callers_of(function_name: str) -> list[str]:
    """Return the names of all functions that call *function_name*."""
    ql = render_template("callers_of.ql.j2", {"target_name": function_name})
    rows = run_codeql_query(ql)
    return _unique([r["col1"] for r in rows if "col1" in r])


def query_variables_defined(function_name: str) -> list[str]:
    """Return the names of all variables defined inside *function_name*."""
    ql = render_template("variables_defined.ql.j2", {"function_name": function_name})
    rows = run_codeql_query(ql)
    return _unique([r["col1"] for r in rows if "col1" in r])


def query_branch_count(function_name: str) -> int:
    """Return the number of branches inside *function_name*."""
    ql = render_template("branch_count.ql.j2", {"function_name": function_name})
    rows = run_codeql_query(ql)
    values = [r["col1"] for r in rows if "col1" in r]
    return int(values[0]) if values else 0


COVERAGE_FILE = SCRIPT_DIR / "hypothesis_coverage.json"


def query_coverage(function_name: str) -> dict:
    """Return (lines_covered, lines_in_function) for *function_name*.

    Reads directly from hypothesis_coverage.json. The function key may be
    plain ("my_func") or class-qualified ("MyClass.my_func").
    """
    if not COVERAGE_FILE.exists():
        raise FileNotFoundError(f"Coverage file not found: {COVERAGE_FILE}")

    with open(COVERAGE_FILE, encoding="utf-8") as fh:
        cov = json.load(fh)

    files = cov.get("files", {})
    if not files:
        raise RuntimeError("No files found in coverage data")

    file_data = next(iter(files.values()))
    functions = file_data.get("functions", {})

    # Match plain name or any "ClassName.function_name" entry
    match = None
    for key, data in functions.items():
        if key == function_name or key.endswith("." + function_name):
            match = data
            break

    if match is None:
        raise RuntimeError(f"Function '{function_name}' not found in coverage data")

    return {
        "lines_covered":      match["summary"]["covered_lines"],
        "lines_in_function":  match["summary"]["num_statements"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="query_system",
        description=(
            "Run parameterised CodeQL queries against a Python CodeQL database. "
            "Database must be named 'codeql-db' in the current directory. "
            "The 'codeql' CLI must be on PATH. "
            "Run 'codeql pack install' once before first use."
        ),
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p1 = subparsers.add_parser("calls-made", help="List all functions that a given function calls.")
    p1.add_argument("--function", required=True, metavar="NAME", help="Name of the caller function")

    p2 = subparsers.add_parser("callers-of", help="List all functions that call a given function.")
    p2.add_argument("--function", required=True, metavar="NAME", help="Name of the target function")

    p3 = subparsers.add_parser("variables", help="List all variables defined inside a given function.")
    p3.add_argument("--function", required=True, metavar="NAME", help="Name of the function to inspect")

    p4 = subparsers.add_parser("branches", help="Count the number of branches inside a given function.")
    p4.add_argument("--function", required=True, metavar="NAME", help="Name of the function to inspect")

    p5 = subparsers.add_parser("coverage", help="Get coverage for a given function from hypothesis_coverage.json.")
    p5.add_argument("--function", required=True, metavar="NAME", help="Name of the function to inspect")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "calls-made": query_calls_made,
        "callers-of": query_callers_of,
        "variables":  query_variables_defined,
        "branches":   query_branch_count,
        "coverage":   query_coverage,
    }

    try:
        results = dispatch[args.command](function_name=args.function)
    except (FileNotFoundError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2 if args.pretty else None))
        sys.exit(1)

    print(json.dumps(results, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()