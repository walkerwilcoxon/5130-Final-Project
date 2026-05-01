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
CODEQL_EXE = "codeql"
GRAPH_DB_DIR    = SCRIPT_DIR / "graph_database"
CALL_GRAPH_FILE = GRAPH_DB_DIR / "call_graph.json"
VAR_DEP_FILE    = GRAPH_DB_DIR / "variable_dependency_graph.json"


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


def _load_call_graph() -> dict:
    if not CALL_GRAPH_FILE.exists():
        raise FileNotFoundError("call_graph.json not found. Run 'generate-call-graph' first.")
    with open(CALL_GRAPH_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _load_var_dep_graph() -> dict:
    if not VAR_DEP_FILE.exists():
        raise FileNotFoundError("variable_dependency_graph.json not found. Run 'generate-variable-dependencies' first.")
    with open(VAR_DEP_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _transitive_calls(graph: dict, start: str) -> list[str]:
    """BFS over call graph from *start*, returning all reachable function names."""
    visited = []
    seen = {start}
    queue = list(graph.get(start, []))
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        visited.append(node)
        queue.extend(n for n in graph.get(node, []) if n not in seen)
    return visited


def _transitive_callers(graph: dict, target: str) -> list[str]:
    """BFS over reversed call graph from *target*, returning all functions that can reach it."""
    # Build reverse graph
    reverse: dict = {}
    for caller, callees in graph.items():
        for callee in callees:
            reverse.setdefault(callee, []).append(caller)
    visited = []
    seen = {target}
    queue = list(reverse.get(target, []))
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        visited.append(node)
        queue.extend(n for n in reverse.get(node, []) if n not in seen)
    return visited


def _transitive_var_deps(graph: dict, function_name: str, variable_name: str) -> list[str]:
    """BFS over variable dependency graph, returning all transitive dependencies."""
    func_graph = graph.get(function_name, {})
    visited = []
    seen = {variable_name}
    queue = list(func_graph.get(variable_name, []))
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        visited.append(node)
        queue.extend(n for n in func_graph.get(node, []) if n not in seen)
    return visited


def query_calls_made(function_name: str, transitive: bool = False) -> list[str]:
    """Return functions that *function_name* calls (direct or transitive)."""
    graph = _load_call_graph()
    if transitive:
        return _transitive_calls(graph, function_name)
    return graph.get(function_name, [])


def query_callers_of(function_name: str, transitive: bool = False) -> list[str]:
    """Return functions that call *function_name* (direct or transitive)."""
    graph = _load_call_graph()
    if transitive:
        return _transitive_callers(graph, function_name)
    return _unique([caller for caller, callees in graph.items() if function_name in callees])


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


COVERAGE_FILE = SCRIPT_DIR / "test_results" / "fuzzing" / "hypothesis" / "raw" / "coverage.json"


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


def query_call_graph() -> dict:
    """Build the full call graph, write it to call_graph.json, and return it."""
    ql = render_template("call_graph.ql.j2", {})
    rows = run_codeql_query(ql)
    graph = {}
    for row in rows:
        val = row.get("col1", "")
        if "," not in val:
            continue
        caller, callee = val.split(",", 1)
        if caller not in graph:
            graph[caller] = []
        if callee not in graph[caller]:
            graph[caller].append(callee)
    GRAPH_DB_DIR.mkdir(parents=True, exist_ok=True)
    with open(CALL_GRAPH_FILE, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)
    return graph


def query_variable_dependencies() -> dict:
    """Build variable dependency graph, write it to variable_dependency_graph.json, and return it."""
    ql = render_template("variable_dependencies.ql.j2", {})
    rows = run_codeql_query(ql)
    result = {}
    for row in rows:
        val = row.get("col1", "")
        parts = val.split(",", 2)
        if len(parts) != 3:
            continue
        func, lhs, rhs = parts
        if func not in result:
            result[func] = {}
        if lhs not in result[func]:
            result[func][lhs] = []
        # rhs is empty string for variables with no dependencies
        if rhs and rhs not in result[func][lhs]:
            result[func][lhs].append(rhs)
    GRAPH_DB_DIR.mkdir(parents=True, exist_ok=True)
    with open(VAR_DEP_FILE, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return result


def query_taint_from_input(function_name: str) -> list[dict]:
    """
    Return all locations where a value tainted by input() reaches
    an argument of *function_name*, as [{"line": <source line>}, ...].
    """
    ql = render_template("taint_from_input.ql.j2", {"function_name": function_name})
    rows = run_codeql_query(ql)
    results = []
    seen = set()
    for row in rows:
        val = row.get("col1", "")
        if not val or val in seen:
            continue
        seen.add(val)
        parts = val.split(",", 1)
        line_str = parts[0]
        var_name = parts[1] if len(parts) > 1 else "<unknown>"
        try:
            results.append({"line": int(line_str), "variable": var_name})
        except ValueError:
            results.append({"line": line_str, "variable": var_name})
    return results


def query_variable_deps_for(function_name: str, variable_name: str, transitive: bool = False) -> list[str]:
    """Return variables that *variable_name* depends on in *function_name* (direct or transitive)."""
    graph = _load_var_dep_graph()
    if transitive:
        return _transitive_var_deps(graph, function_name, variable_name)
    return graph.get(function_name, {}).get(variable_name, [])


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
    subparsers = parser.add_subparsers(dest="command", required=True)

    p1 = subparsers.add_parser("calls-made", help="List all functions that a given function calls.")
    p1.add_argument("--function", required=True, metavar="NAME", help="Name of the caller function")
    p1.add_argument("--transitive", action="store_true", help="Include transitive callees (default: direct only)")

    p2 = subparsers.add_parser("callers-of", help="List all functions that call a given function.")
    p2.add_argument("--function", required=True, metavar="NAME", help="Name of the target function")
    p2.add_argument("--transitive", action="store_true", help="Include transitive callers (default: direct only)")

    p3 = subparsers.add_parser("variables", help="List all variables defined inside a given function.")
    p3.add_argument("--function", required=True, metavar="NAME", help="Name of the function to inspect")

    p4 = subparsers.add_parser("branches", help="Count the number of branches inside a given function.")
    p4.add_argument("--function", required=True, metavar="NAME", help="Name of the function to inspect")

    p5 = subparsers.add_parser("coverage", help="Get coverage for a given function from hypothesis_coverage.json.")
    p5.add_argument("--function", required=True, metavar="NAME", help="Name of the function to inspect")

    subparsers.add_parser("generate-call-graph", help="Generate the full call graph of the project.")

    subparsers.add_parser("generate-variable-dependencies", help="Get variable dependencies for all functions.")

    p_taint = subparsers.add_parser("taint", help="Check if a function receives tainted input() values.")
    p_taint.add_argument("--function", required=True, metavar="NAME", help="Name of the function to check")

    p_vdf = subparsers.add_parser("var-deps-for", help="Get dependencies of a variable in a function.")
    p_vdf.add_argument("--function", required=True, metavar="NAME", help="Name of the function")
    p_vdf.add_argument("--variable", required=True, metavar="NAME", help="Name of the variable")
    p_vdf.add_argument("--transitive", action="store_true", help="Include transitive dependencies (default: direct only)")

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
        "taint":      query_taint_from_input,
    }

    try:
        if args.command == "generate-call-graph":
            results = query_call_graph()
        elif args.command == "generate-variable-dependencies":
            results = query_variable_dependencies()
        elif args.command == "var-deps-for":
            results = query_variable_deps_for(
                function_name=args.function,
                variable_name=args.variable,
                transitive=getattr(args, "transitive", False),
            )
        else:
            transitive = getattr(args, "transitive", False)
            if transitive:
                results = dispatch[args.command](function_name=args.function, transitive=True)
            else:
                results = dispatch[args.command](function_name=args.function)
    except (FileNotFoundError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        sys.exit(1)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()