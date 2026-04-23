"""Natural-language query interface for static-analysis results.

Scope: supports exactly 8 query families.
Target source (default): course_management_system.py
"""

from __future__ import annotations

import ast
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Set


class QueryType(str, Enum):
    DEAD_CODE = "q1_dead_code"
    VARS_DEFINED = "q2_vars_defined"
    VAR_LIVE_AT_POINT = "q3_var_live_at_point"
    CALLEES = "q4_callees"
    TRANSITIVE_CALL_CHAIN = "q5_transitive_call_chain"
    HOTSPOTS = "q6_hotspots"
    LINES_COVERED_BY_TESTS = "q7_lines_covered_by_tests"
    TEST_COVERAGE_SUMMARY = "q8_test_coverage_summary"


@dataclass
class QueryCommand:
    query_type: QueryType
    source_file: str = "course_management_system.py"
    function_name: Optional[str] = None
    variable_name: Optional[str] = None
    line: Optional[int] = None
    lines: Optional[List[int]] = None
    top_k: int = 5


class CoverageReportInspector:
    """Loads and answers coverage queries from local fuzzing coverage reports."""

    ATHERIS_COVERAGE_PATH = "test_results/fuzzing/atheris/raw/coverage.json"
    HYPOTHESIS_COVERAGE_PATH = "test_results/fuzzing/hypothesis/raw/coverage.json"

    def __init__(self, source_file: str):
        self.source_file = source_file

    @staticmethod
    def _load_json(path: str) -> Dict[str, Any]:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except OSError as exc:
            raise RuntimeError(f"Could not read coverage file '{path}': {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Coverage file '{path}' is not valid JSON: {exc}") from exc

    @staticmethod
    def _find_file_coverage(report: Dict[str, Any], source_file: str) -> Optional[Dict[str, Any]]:
        files = report.get("files")
        if not isinstance(files, dict):
            return None

        if source_file in files and isinstance(files[source_file], dict):
            return files[source_file]

        src_name = Path(source_file).name
        for file_key, file_value in files.items():
            if not isinstance(file_value, dict):
                continue
            if Path(str(file_key)).name == src_name:
                return file_value

        return None

    @staticmethod
    def _to_line_set(value: Any) -> Set[int]:
        if not isinstance(value, list):
            return set()
        out: Set[int] = set()
        for item in value:
            if isinstance(item, int) and item > 0:
                out.add(item)
        return out

    @staticmethod
    def _summary_from_file_coverage(file_cov: Dict[str, Any]) -> Dict[str, Any]:
        summary = file_cov.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        return {
            "covered_lines": int(summary.get("covered_lines", 0) or 0),
            "num_statements": int(summary.get("num_statements", 0) or 0),
            "percent_covered": float(summary.get("percent_covered", 0.0) or 0.0),
            "percent_covered_display": str(summary.get("percent_covered_display", "0")),
            "missing_lines": int(summary.get("missing_lines", 0) or 0),
        }

    def _load_reports(self) -> Dict[str, Dict[str, Any]]:
        reports: Dict[str, Dict[str, Any]] = {}
        for name, path in {
            "atheris": self.ATHERIS_COVERAGE_PATH,
            "hypothesis": self.HYPOTHESIS_COVERAGE_PATH,
        }.items():
            report = self._load_json(path)
            file_cov = self._find_file_coverage(report, self.source_file)
            if file_cov is None:
                reports[name] = {
                    "path": path,
                    "file_coverage": None,
                    "executed": set(),
                    "summary": {},
                }
                continue

            executed = self._to_line_set(file_cov.get("executed_lines", []))
            reports[name] = {
                "path": path,
                "file_coverage": file_cov,
                "executed": executed,
                "summary": self._summary_from_file_coverage(file_cov),
            }
        return reports

    def _analyze_source_lines(self) -> Dict[str, Any]:
        """Analyze source lines for coverage-display semantics.

        Returns:
        - excluded_lines: 1-based lines to exclude from coverage checks.
        - continuation_anchor: mapping of line -> logical statement start line.
        - clause_body_map: mapping of clause header line -> lines in its indented block.

        Excluded categories include:
        - blank/whitespace-only lines
        - comment-only lines
        - docstring lines (module/class/function leading string literal)
        - standalone string-literal expression blocks
        """
        try:
            source = Path(self.source_file).read_text(encoding="utf-8")
        except OSError:
            return {
                "excluded_lines": set(),
                "continuation_anchor": {},
                "clause_body_map": {},
            }

        lines = source.splitlines()
        excluded: Set[int] = set()
        continuation_anchor: Dict[int, int] = {}
        clause_body_map: Dict[int, Set[int]] = {}

        # Blank lines.
        for idx, line in enumerate(lines, start=1):
            if not line.strip():
                excluded.add(idx)

        # Comment-only lines via tokenize (ignores inline comments with code before '#').
        try:
            import io
            import token
            import tokenize

            tok_iter = tokenize.generate_tokens(io.StringIO(source).readline)
            for tok in tok_iter:
                if tok.type != tokenize.COMMENT:
                    continue
                line_no = int(tok.start[0])
                col = int(tok.start[1])
                raw_line = lines[line_no - 1] if 1 <= line_no <= len(lines) else ""
                if raw_line[:col].strip() == "":
                    excluded.add(line_no)
        except Exception:
            # Keep best-effort behavior if tokenization fails on transient syntax issues.
            pass

        # Logical statement anchoring for multiline statements/headers.
        # Example: multiline def signature lines all anchor to the `def` line.
        try:
            import io
            import token
            import tokenize

            logical_start: Optional[int] = None
            tok_iter = tokenize.generate_tokens(io.StringIO(source).readline)
            for tok in tok_iter:
                tok_type = tok.type
                sline = int(tok.start[0])
                eline = int(tok.end[0])

                if tok_type in {tokenize.ENCODING, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}:
                    if tok_type == tokenize.NEWLINE:
                        logical_start = None
                    continue

                if logical_start is None:
                    logical_start = sline

                for ln in range(sline, eline + 1):
                    if ln > 0:
                        continuation_anchor.setdefault(ln, logical_start)
        except Exception:
            pass

        # Clause header -> inner block mapping using indentation scanning.
        clause_header = re.compile(
            r"^(else:|elif\b.*:|except\b.*:|finally:|case\b.*:)$",
            re.IGNORECASE,
        )
        total = len(lines)
        for i, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if not clause_header.match(stripped):
                continue

            indent = len(raw) - len(raw.lstrip(" "))
            block_lines: Set[int] = set()
            j = i + 1
            while j <= total:
                probe = lines[j - 1]
                probe_stripped = probe.strip()

                if not probe_stripped:
                    j += 1
                    continue

                probe_indent = len(probe) - len(probe.lstrip(" "))

                # End of this clause block when indentation returns to same-or-less level.
                if probe_indent <= indent:
                    break

                block_lines.add(j)
                j += 1

            if block_lines:
                clause_body_map[i] = block_lines

        # Docstring lines for module/class/function scopes.
        try:
            tree = ast.parse(source, filename=self.source_file)

            def _mark_scope_docstring(scope: Any) -> None:
                body = getattr(scope, "body", None)
                if not isinstance(body, list) or not body:
                    return
                first = body[0]
                if not isinstance(first, ast.Expr):
                    return
                value = first.value
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    return

                start = int(getattr(first, "lineno", 0) or 0)
                end = int(getattr(first, "end_lineno", start) or start)
                if start <= 0:
                    return
                for ln in range(start, end + 1):
                    excluded.add(ln)

            _mark_scope_docstring(tree)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    _mark_scope_docstring(node)

            # Any standalone string literal expression is comment-like noise for
            # this UI's coverage intent (e.g., large prompt blocks in triple quotes).
            for node in ast.walk(tree):
                if not isinstance(node, ast.Expr):
                    continue
                value = node.value
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                start = int(getattr(node, "lineno", 0) or 0)
                end = int(getattr(node, "end_lineno", start) or start)
                if start <= 0:
                    continue
                for ln in range(start, end + 1):
                    excluded.add(ln)
        except SyntaxError:
            pass

        return {
            "excluded_lines": excluded,
            "continuation_anchor": continuation_anchor,
            "clause_body_map": clause_body_map,
        }

    def lines_covered(self, lines: List[int]) -> Dict[str, Any]:
        normalized: List[int] = []
        seen: Set[int] = set()
        for ln in lines:
            if isinstance(ln, int) and ln > 0 and ln not in seen:
                seen.add(ln)
                normalized.append(ln)

        if not normalized:
            return {
                "error": "No valid line numbers were provided.",
                "hint": "Try a query like: Are lines 423, 547, 900 covered by tests?",
            }

        source_analysis = self._analyze_source_lines()
        excluded_lines = set(source_analysis.get("excluded_lines", set()))
        continuation_anchor = dict(source_analysis.get("continuation_anchor", {}))
        clause_body_map = {
            int(k): set(v)
            for k, v in dict(source_analysis.get("clause_body_map", {})).items()
            if isinstance(k, int)
        }
        effective_lines = [ln for ln in normalized if ln not in excluded_lines]

        if not effective_lines:
            return {
                "source_file": self.source_file,
                "query_lines": [],
                "requested_lines": normalized,
                "excluded_non_code_lines": [ln for ln in normalized if ln in excluded_lines],
                "covered_lines": 0,
                "total_lines": 0,
                "all_lines_covered": False,
                "per_line": [],
                "note": "All requested lines are blank/comment/docstring lines and were excluded.",
                "reports": {
                    "atheris": self.ATHERIS_COVERAGE_PATH,
                    "hypothesis": self.HYPOTHESIS_COVERAGE_PATH,
                },
            }

        reports = self._load_reports()
        available_reports: List[str] = [
            name for name, payload in reports.items() if payload.get("file_coverage") is not None
        ]
        if not available_reports:
            available_reports = list(reports.keys())

        executed_by_report: Dict[str, Set[int]] = {
            name: set(payload.get("executed", set())) for name, payload in reports.items()
        }
        total_runs = max(1, len(available_reports))

        per_line: List[Dict[str, Any]] = []
        effective_line_set = set(effective_lines)
        row_by_line: Dict[int, Dict[str, Any]] = {}
        for ln in effective_lines:
            anchor_line = int(continuation_anchor.get(ln, ln))
            by_atheris = anchor_line in executed_by_report.get("atheris", set())
            by_hypothesis = anchor_line in executed_by_report.get("hypothesis", set())
            covered_any = by_atheris or by_hypothesis
            coverage_hits = sum(
                1 for report_name in available_reports if anchor_line in executed_by_report.get(report_name, set())
            )
            coverage_rate = (coverage_hits / total_runs) * 100.0

            atheris_total = 1 if "atheris" in available_reports else 0
            hypothesis_total = 1 if "hypothesis" in available_reports else 0
            atheris_hits = 1 if by_atheris and atheris_total > 0 else 0
            hypothesis_hits = 1 if by_hypothesis and hypothesis_total > 0 else 0
            atheris_rate = (atheris_hits / atheris_total) * 100.0 if atheris_total > 0 else 0.0
            hypothesis_rate = (hypothesis_hits / hypothesis_total) * 100.0 if hypothesis_total > 0 else 0.0

            row = {
                "line": ln,
                "anchor_line": anchor_line,
                "covered": covered_any,
                "coverage_hits": coverage_hits,
                "coverage_total": total_runs,
                "coverage_rate": round(coverage_rate, 4),
                "covered_by": {
                    "atheris": by_atheris,
                    "hypothesis": by_hypothesis,
                },
                "coverage_by_tool": {
                    "atheris": {
                        "hits": atheris_hits,
                        "total": atheris_total,
                        "rate": round(atheris_rate, 4),
                    },
                    "hypothesis": {
                        "hits": hypothesis_hits,
                        "total": hypothesis_total,
                        "rate": round(hypothesis_rate, 4),
                    },
                },
            }
            row_by_line[ln] = row
            per_line.append(row)

        # Clause lines (else/elif/except/finally/case) are treated as normal lines:
        # green if any line in their inner block is green; red only if all are red.
        for clause_line, body_lines in clause_body_map.items():
            if clause_line not in effective_line_set:
                continue

            relevant = [ln for ln in sorted(body_lines) if ln in effective_line_set]
            if not relevant:
                continue

            body_rows = [row_by_line.get(ln) for ln in relevant if isinstance(row_by_line.get(ln), dict)]
            if not body_rows:
                continue

            clause_row = row_by_line.get(clause_line)
            if not isinstance(clause_row, dict):
                continue

            by_atheris_clause = any(bool(br.get("covered_by", {}).get("atheris", False)) for br in body_rows)
            by_hypothesis_clause = any(bool(br.get("covered_by", {}).get("hypothesis", False)) for br in body_rows)
            coverage_hits_clause = int(by_atheris_clause) + int(by_hypothesis_clause)
            coverage_rate_clause = (coverage_hits_clause / total_runs) * 100.0

            clause_row["covered"] = bool(by_atheris_clause or by_hypothesis_clause)
            clause_row["coverage_hits"] = coverage_hits_clause
            clause_row["coverage_rate"] = round(coverage_rate_clause, 4)
            clause_row["covered_by"] = {
                "atheris": by_atheris_clause,
                "hypothesis": by_hypothesis_clause,
            }

        covered_count = sum(1 for row in per_line if row["covered"])
        return {
            "source_file": self.source_file,
            "query_lines": effective_lines,
            "requested_lines": normalized,
            "excluded_non_code_lines": [ln for ln in normalized if ln in excluded_lines],
            "covered_lines": covered_count,
            "total_lines": len(effective_lines),
            "all_lines_covered": covered_count == len(effective_lines),
            "per_line": per_line,
            "reports": {
                "atheris": reports["atheris"]["path"],
                "hypothesis": reports["hypothesis"]["path"],
            },
        }

    def suite_coverage(self) -> Dict[str, Any]:
        reports = self._load_reports()
        atheris_summary = reports["atheris"]["summary"]
        hypothesis_summary = reports["hypothesis"]["summary"]

        union_executed = set(reports["atheris"]["executed"]) | set(reports["hypothesis"]["executed"])

        num_statements_candidates: List[int] = []
        for item in (atheris_summary, hypothesis_summary):
            if isinstance(item, dict):
                n = int(item.get("num_statements", 0) or 0)
                if n > 0:
                    num_statements_candidates.append(n)
        combined_num_statements = max(num_statements_candidates) if num_statements_candidates else 0

        combined_percent = (
            (len(union_executed) / combined_num_statements) * 100.0 if combined_num_statements > 0 else 0.0
        )

        return {
            "source_file": self.source_file,
            "reports": {
                "atheris": {
                    "path": reports["atheris"]["path"],
                    "summary": atheris_summary,
                },
                "hypothesis": {
                    "path": reports["hypothesis"]["path"],
                    "summary": hypothesis_summary,
                },
            },
            "combined": {
                "strategy": "union_of_executed_lines",
                "covered_lines": len(union_executed),
                "num_statements": combined_num_statements,
                "percent_covered": round(combined_percent, 6),
                "percent_covered_display": f"{combined_percent:.2f}",
            },
        }


class QueryBackend(Protocol):

    def has_dead_code(self, source_file: str) -> Dict[str, Any]:
        ...

    def variables_defined(self, source_file: str, function_name: str) -> Dict[str, Any]:
        ...

    def is_variable_live(
        self,
        source_file: str,
        function_name: str,
        variable_name: str,
        line: int,
    ) -> Dict[str, Any]:
        ...

    def functions_called_by(self, source_file: str, function_name: str) -> Dict[str, Any]:
        ...

    def transitive_call_chain(self, source_file: str, function_name: str) -> Dict[str, Any]:
        ...

    def hotspots(self, source_file: str, top_k: int = 5) -> Dict[str, Any]:
        ...


class AIClient(Protocol):
    """Minimal protocol for an LLM client used by the query interface."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...


class OpenAICompatibleAIClient:
    """HTTP client for OpenAI-compatible chat-completions endpoints.

    Works with OpenAI and gateways that mimic the same API shape.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_json = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AI API HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"AI API request failed: {exc}") from exc

        try:
            return response_json["choices"][0]["message"]["content"]
        except Exception as exc:  # pragma: no cover - defensive parsing
            raise RuntimeError(f"Unexpected AI response shape: {response_json}") from exc


def load_dotenv_file(path: str = ".env", override: bool = False) -> None:
    """Load key/value pairs from a .env file into process environment.

    - Ignores empty lines and comments.
    - Supports quoted values.
    - By default, does not override existing environment variables.
    """
    dotenv_path = Path(path)
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return

    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if not override and key in os.environ and os.environ.get(key, ""):
            continue
        os.environ[key] = value


def make_ai_client_from_env() -> Optional[OpenAICompatibleAIClient]:
    """Creates an OpenAI-compatible client from environment variables.

    Expected variables:
      - OPENAI_API_KEY
      - OPENAI_MODEL (optional, default gpt-4o-mini)
      - OPENAI_BASE_URL (optional)
    """
    load_dotenv_file()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1"
    return OpenAICompatibleAIClient(api_key=api_key, model=model, base_url=base_url)


class SourceInspector:
    """Fallback source-based answers when API data is unavailable.

    This is intentionally conservative and approximate for Q1/Q3/Q6.
    """

    def __init__(self, source_file: str):
        self.source_file = source_file
        source = Path(source_file).read_text(encoding="utf-8")
        self.tree = ast.parse(source, filename=source_file)
        self.functions: Dict[str, ast.FunctionDef] = {}
        self._line_count: Dict[str, int] = {}
        self._call_graph: Dict[str, Set[str]] = {}
        self._build_indexes()

    def _build_indexes(self) -> None:
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef):
                self.functions[node.name] = node
                self._line_count[node.name] = (node.end_lineno or node.lineno) - node.lineno + 1

        for name, fn in self.functions.items():
            calls = set()
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Call):
                    callee = self._call_name(sub.func)
                    if callee:
                        calls.add(callee)
            self._call_graph[name] = calls

    @staticmethod
    def _call_name(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def variables_defined(self, function_name: str) -> List[str]:
        fn = self.functions.get(function_name)
        if fn is None:
            return []
        defs: Set[str] = set(arg.arg for arg in fn.args.args)
        defs |= set(arg.arg for arg in fn.args.kwonlyargs)
        if fn.args.vararg:
            defs.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            defs.add(fn.args.kwarg.arg)

        for sub in ast.walk(fn):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                defs.add(sub.id)
        return sorted(defs)

    def functions_called_by(self, function_name: str) -> List[str]:
        return sorted(self._call_graph.get(function_name, set()))

    def transitive_call_chain(self, function_name: str) -> List[str]:
        visited: Set[str] = set()
        stack = [function_name]

        while stack:
            current = stack.pop()
            for callee in self._call_graph.get(current, set()):
                if callee not in visited:
                    visited.add(callee)
                    if callee in self.functions:
                        stack.append(callee)

        visited.discard(function_name)
        return sorted(visited)

    def has_dead_code(self) -> Dict[str, Any]:
        top_level_roots: Set[str] = set()

        for node in self.tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                callee = self._call_name(node.value.func)
                if callee:
                    top_level_roots.add(callee)
            if isinstance(node, ast.If):
                # Include calls inside if __name__ == "__main__":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        callee = self._call_name(sub.func)
                        if callee:
                            top_level_roots.add(callee)

        reachable: Set[str] = set()
        stack = list(top_level_roots)
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            for nxt in self._call_graph.get(cur, set()):
                if nxt in self.functions and nxt not in reachable:
                    stack.append(nxt)

        all_functions = set(self.functions.keys())
        dead = sorted(all_functions - reachable)
        return {
            "has_dead_code": bool(dead),
            "dead_functions": dead,
            "reachable_roots": sorted(top_level_roots),
            "note": "Approximate source-based reachability (no dynamic dispatch).",
        }

    def is_variable_live(self, function_name: str, variable_name: str, line: int) -> Dict[str, Any]:
        fn = self.functions.get(function_name)
        if fn is None:
            return {"error": f"Function '{function_name}' not found."}

        uses_after: List[int] = []
        defs_after: List[int] = []

        for sub in ast.walk(fn):
            if isinstance(sub, ast.Name) and sub.id == variable_name and hasattr(sub, "lineno"):
                if sub.lineno > line:
                    if isinstance(sub.ctx, ast.Load):
                        uses_after.append(sub.lineno)
                    elif isinstance(sub.ctx, ast.Store):
                        defs_after.append(sub.lineno)

        uses_after.sort()
        defs_after.sort()

        if not uses_after:
            return {
                "is_live": False,
                "reason": "No future use found in function after the given line.",
            }

        first_use = uses_after[0]
        first_def = defs_after[0] if defs_after else None
        is_live = first_def is None or first_use < first_def

        return {
            "is_live": is_live,
            "first_use_after_line": first_use,
            "first_redefinition_after_line": first_def,
            "note": "Path-insensitive approximation from AST uses/defs.",
        }

    def hotspots(self, top_k: int = 5) -> List[Dict[str, Any]]:
        fan_in: Dict[str, int] = {f: 0 for f in self.functions}
        fan_out: Dict[str, int] = {f: 0 for f in self.functions}

        for caller, callees in self._call_graph.items():
            internal_callees = [c for c in callees if c in self.functions]
            fan_out[caller] = len(set(internal_callees))
            for callee in internal_callees:
                fan_in[callee] += 1

        rows = []
        for fn, node in self.functions.items():
            stmt_count = sum(1 for _ in ast.walk(node))
            score = fan_in[fn] * 2 + fan_out[fn] * 1.5 + self._line_count.get(fn, 0) * 0.1 + stmt_count * 0.03
            rows.append(
                {
                    "function": fn,
                    "score": round(score, 3),
                    "fan_in": fan_in[fn],
                    "fan_out": fan_out[fn],
                    "lines": self._line_count.get(fn, 0),
                }
            )

        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows[: max(1, top_k)]


class NLQueryMapper:
    """Maps natural language to one of the six supported QueryCommand types."""

    _func = r"(?P<func>[A-Za-z_][A-Za-z0-9_]*)"
    _var = r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
    _line = r"(?P<line>\d+)"

    @staticmethod
    def _extract_line_numbers(text: str) -> List[int]:
        nums: List[int] = []
        seen: Set[int] = set()

        def _add(n: int) -> None:
            if n > 0 and n not in seen:
                seen.add(n)
                nums.append(n)

        def _add_range(a: int, b: int) -> None:
            if a <= 0 or b <= 0:
                return
            lo = min(a, b)
            hi = max(a, b)
            # Safety cap to avoid accidental huge expansions on malformed input.
            if hi - lo > 5000:
                _add(lo)
                _add(hi)
                return
            for n in range(lo, hi + 1):
                _add(n)

        normalized = text.replace("–", "-").replace("—", "-")

        # Range forms: "192-210", "L192-L210", "192 to 210", "line 192 through 210".
        for m in re.finditer(
            r"\b(?:line(?:s)?\s*)?[Ll]?(\d+)\s*(?:-|to|through)\s*(?:[Ll])?(\d+)\b",
            normalized,
            re.IGNORECASE,
        ):
            _add_range(int(m.group(1)), int(m.group(2)))

        # Explicit L-prefixed singles: "L192".
        for m in re.finditer(r"\b[Ll](\d+)\b", normalized):
            _add(int(m.group(1)))

        # Number lists near "line" / "lines": "lines 12, 14 and 18".
        for m in re.finditer(r"\bline(?:s)?\b([^?.!\n\r]*)", normalized, re.IGNORECASE):
            chunk = m.group(1)

            # Expand ranges appearing inside this chunk first.
            for r in re.finditer(r"\b(\d+)\s*(?:-|to|through)\s*(\d+)\b", chunk, re.IGNORECASE):
                _add_range(int(r.group(1)), int(r.group(2)))

            # Then add standalone numbers.
            for token in re.findall(r"\b\d+\b", chunk):
                _add(int(token))

        return nums

    def map_to_command(self, text: str, default_source: str = "course_management_system.py") -> Optional[QueryCommand]:
        q = " ".join(text.strip().split())
        low = q.lower()

        # Q1 dead code
        if any(kw in low for kw in ("dead code", "unreachable", "unused function", "never called")):
            return QueryCommand(query_type=QueryType.DEAD_CODE, source_file=default_source)

        # Q2 variables defined in function F
        m = re.search(rf"variables?\s+(?:are\s+)?defined.*function\s+{self._func}", q, re.IGNORECASE)
        if not m:
            m = re.search(rf"(?:in|inside)\s+{self._func}\s*,?\s*which\s+variables?\s+are\s+defined", q, re.IGNORECASE)
        if m:
            return QueryCommand(
                query_type=QueryType.VARS_DEFINED,
                source_file=default_source,
                function_name=m.group("func"),
            )

        # Q3 variable live at point
        m = re.search(
            rf"is\s+{self._var}\s+live.*(?:line|point)\s+{self._line}.*function\s+{self._func}",
            q,
            re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf"function\s+{self._func}.*is\s+{self._var}\s+live.*(?:line|point)\s+{self._line}",
                q,
                re.IGNORECASE,
            )
        if m:
            return QueryCommand(
                query_type=QueryType.VAR_LIVE_AT_POINT,
                source_file=default_source,
                function_name=m.group("func"),
                variable_name=m.group("var"),
                line=int(m.group("line")),
            )

        # Q4 direct callees
        m = re.search(rf"functions?\s+(?:are\s+)?called\s+by\s+{self._func}\??", q, re.IGNORECASE)
        if not m:
            m = re.search(rf"does\s+{self._func}\s+call", q, re.IGNORECASE)
        if m:
            return QueryCommand(
                query_type=QueryType.CALLEES,
                source_file=default_source,
                function_name=m.group("func"),
            )

        # Q5 transitive call chain
        m = re.search(rf"transitive\s+call\s+chain\s+of\s+{self._func}", q, re.IGNORECASE)
        if not m:
            m = re.search(rf"full\s+call\s+chain\s+of\s+{self._func}", q, re.IGNORECASE)
        if m:
            return QueryCommand(
                query_type=QueryType.TRANSITIVE_CALL_CHAIN,
                source_file=default_source,
                function_name=m.group("func"),
            )

        # Q6 hotspots
        if "hotspot" in low or "hot spot" in low or "most complex" in low:
            top_k = 5
            m = re.search(r"top\s+(\d+)", low)
            if m:
                top_k = int(m.group(1))
            return QueryCommand(query_type=QueryType.HOTSPOTS, source_file=default_source, top_k=top_k)

        # Q7 line coverage check
        if "covered by tests" in low or ("line" in low and "coverage" in low):
            return QueryCommand(
                query_type=QueryType.LINES_COVERED_BY_TESTS,
                source_file=default_source,
                lines=self._extract_line_numbers(q),
            )

        # Q8 suite coverage summary
        if "coverage of the test suite" in low or "test suite coverage" in low:
            return QueryCommand(
                query_type=QueryType.TEST_COVERAGE_SUMMARY,
                source_file=default_source,
            )

        return None


class QueryInterface:
    """Main orchestration layer for NL query => command => API call => response."""

    def __init__(
        self,
        backend: Optional[QueryBackend] = None,
        default_source: str = "course_management_system.py",
        ai_client: Optional[AIClient] = None,
        tool_registry: Optional[Dict[str, Callable[..., Dict[str, Any]]]] = None,
        ai_source_max_chars: int = 40000,
    ):
        self.backend = backend
        self.default_source = default_source
        self.mapper = NLQueryMapper()
        self.ai_client = ai_client
        built_in_tools: Dict[str, Callable[..., Dict[str, Any]]] = {
            "are_lines_covered_by_tests": self.are_lines_covered_by_tests,
            "get_test_suite_coverage": self.get_test_suite_coverage,
        }
        self.tool_registry = {**built_in_tools, **(tool_registry or {})}
        self.ai_source_max_chars = max(1000, ai_source_max_chars)

    def execute(self, natural_language_query: str) -> Dict[str, Any]:
        if self.ai_client is not None:
            ai_result = self._execute_via_ai(natural_language_query)
            if ai_result is not None:
                return ai_result

        command = self.mapper.map_to_command(natural_language_query, default_source=self.default_source)

        if command is None:
            # Fallback: best-effort direct answer from source; otherwise reject.
            return self._fallback_or_reject(natural_language_query)

        if command.query_type == QueryType.LINES_COVERED_BY_TESTS:
            return self.are_lines_covered_by_tests(lines=command.lines or [], source_file=command.source_file)

        if command.query_type == QueryType.TEST_COVERAGE_SUMMARY:
            return self.get_test_suite_coverage(source_file=command.source_file)

        if self.backend is None:
            return self._run_fallback(command)

        return self._dispatch_backend(command)

    def _execute_via_ai(self, natural_language_query: str) -> Optional[Dict[str, Any]]:
        system_prompt = self._build_ai_router_prompt()
        user_prompt = self._build_ai_user_prompt(natural_language_query)
        try:
            raw = self.ai_client.complete(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:
            return {
                "error": "AI routing request failed.",
                "detail": str(exc),
            }

        parsed = self._parse_ai_json(raw)
        if not isinstance(parsed, dict):
            return {
                "error": "AI response was not valid JSON router output.",
                "ai_raw_response": raw,
            }

        action = str(parsed.get("action", "")).strip().lower()
        query_type = str(parsed.get("query_type", "other"))
        related_lines = self._normalize_line_numbers(parsed.get("related_lines", []))
        related_lines = self._sanitize_related_lines(related_lines)

        if action == "answer_from_source":
            can_answer = bool(parsed.get("can_answer", True))
            if can_answer:
                out = {
                    "answer": parsed.get("answer", ""),
                    "mode": "ai-source-answer",
                    "query_type": query_type,
                }
                if related_lines:
                    out["related_lines"] = related_lines
                return out
            return {
                "answer": parsed.get("answer", "I cannot answer this reliably from the available source code."),
                "mode": "ai-source-answer",
                "query_type": query_type,
                "can_answer": False,
                "reason": parsed.get("reason", "Insufficient evidence from source code."),
                "related_lines": related_lines,
            }

        if action == "call_local_api":
            tool_name = parsed.get("tool_name")
            arguments = parsed.get("arguments", {})
            if not isinstance(tool_name, str) or not tool_name.strip():
                return {
                    "error": "AI requested tool call without a valid tool_name.",
                    "ai_router_output": parsed,
                }
            if not isinstance(arguments, dict):
                return {
                    "error": "AI requested tool call with non-dict arguments.",
                    "ai_router_output": parsed,
                }

            # For q7 line coverage, AI only decides whether line numbers are present.
            # We always parse all actual line numbers locally from the user query.
            if isinstance(tool_name, str) and tool_name.strip() == "are_lines_covered_by_tests":
                has_line_numbers = bool(arguments.get("has_line_numbers", False))
                source_file = str(arguments.get("source_file", self.default_source)).strip() or self.default_source
                if not has_line_numbers:
                    return {
                        "mode": "ai-source-answer",
                        "query_type": query_type,
                        "can_answer": False,
                        "reason": "Please include at least one line number to check coverage.",
                        "related_lines": [],
                    }
                arguments = {
                    "source_file": source_file,
                    "lines": self.mapper._extract_line_numbers(natural_language_query),
                }

            result = self._invoke_flexible_tool(tool_name.strip(), arguments)
            if "error" not in result:
                result["status"] = "AI mapped the query to a local API call and the call was executed."
                result["query_type"] = query_type
            return result

        if action == "cannot_answer":
            return {
                "mode": "ai-source-answer",
                "query_type": query_type,
                "can_answer": False,
                "reason": parsed.get("reason", "AI could not determine a reliable answer."),
                "related_lines": related_lines,
            }

        if action == "delegate_to_regex":
            return None

        return {
            "error": "AI router returned unknown action.",
            "ai_router_output": parsed,
        }

    def _build_ai_router_prompt(self) -> str:
        available_tools = sorted(set(self.tool_registry.keys()) | self._discover_backend_methods())
        tool_doc = "\n".join(f"- {name}" for name in available_tools) if available_tools else "- (none currently wired)"

        return (
            "You are a query router and answerer for static-analysis or testing questions over a Python source file.\n"
            "Return ONLY JSON, no markdown.\n"
            "Allowed JSON formats:\n"
            "1) {\"action\":\"call_local_api\",\"query_type\":\"...\",\"tool_name\":\"...\",\"arguments\":{...}}\n"
            "2) {\"action\":\"answer_from_source\",\"query_type\":\"...\",\"can_answer\":true,\"answer\":\"...\",\"related_lines\":[]}\n"
            "3) {\"action\":\"cannot_answer\",\"query_type\":\"...\",\"reason\":\"...\",\"related_lines\":[...]}\n"
            "4) {\"action\":\"delegate_to_regex\"}\n"
            "Supported query types: q1_dead_code, q2_vars_defined, q3_var_live_at_point, q4_callees, q5_transitive_call_chain, q6_hotspots, q7_lines_covered_by_tests, q8_test_coverage_summary, other.\n"
            "Decision policy:\n"
            "- If query is not related to the analysis or testing of the source code or it is not a valid query, return cannot_answer.\n"
            "- If query is one of the supported types AND a suitable local tool exists, return call_local_api.\n"
            "- If query is one of the supported types but no suitable local tool exists, inspect source and return answer_from_source or cannot_answer.\n"
            "- If query is not one of the supported types, inspect source and return answer_from_source or cannot_answer.\n"
            "- Never invent tool names; choose only from available tools listed below.\n"
            "- For answer_from_source, include related_lines as the most relevant 1-based source line numbers when possible.\n"
            "- The source snippet you receive is line-numbered (e.g., ' 123: code'). Use those exact numbers in related_lines.\n"
            "- related_lines must be grounded in the provided source snippet, not guessed.\n"
            "- The number of lines should be minimal and directly relevant. Do not include lines that only contain comments or whitespace.\n"
            "- Do NOT use placeholder or repeated canned line numbers. If uncertain, use an empty list [].\n"
            "Known available tool names right now:\n"
            f"{tool_doc}\n"
            "Query type -> tool correspondence and required arguments:\n"
            "- q7_lines_covered_by_tests -> are_lines_covered_by_tests(arguments={\"source_file\": \"...\", \"has_line_numbers\": true|false})\n"
            "  IMPORTANT: Do NOT extract or list line numbers in arguments. Only decide whether the query contains at least one line number.\n"
            "  The runtime will parse all line numbers locally and process coverage locally.\n"
            "- q8_test_coverage_summary -> get_test_suite_coverage(arguments={\"source_file\": \"...\"})\n"
            "Important: arguments must be a JSON object with primitive values/arrays/objects only."
        )

    @staticmethod
    def _normalize_lines_arg(value: Any) -> List[int]:
        if not isinstance(value, list):
            return []
        out: List[int] = []
        seen: Set[int] = set()
        for item in value:
            n: Optional[int] = None
            if isinstance(item, int):
                n = item
            elif isinstance(item, str) and item.strip().isdigit():
                n = int(item.strip())
            if n is not None and n > 0 and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    @staticmethod
    def _format_lines_coverage_answer(result: Dict[str, Any]) -> str:
        if "error" in result:
            hint = str(result.get("hint", "")).strip()
            msg = f"Could not evaluate line coverage: {result.get('error', 'Unknown error.')}"
            if hint:
                msg += f"\nHint: {hint}"
            return msg

        source_file = str(result.get("source_file", "<unknown source>"))
        covered_lines = int(result.get("covered_lines", 0) or 0)
        total_lines = int(result.get("total_lines", 0) or 0)
        all_covered = bool(result.get("all_lines_covered", False))

        lines = [
            "Coverage Check (Specific Lines)",
            f"Source: {source_file}",
            f"Summary: {covered_lines}/{total_lines} line(s) covered by at least one test run.",
            "",
            "Details:",
        ]

        for row in result.get("per_line", []):
            if not isinstance(row, dict):
                continue
            ln = row.get("line")
            covered = bool(row.get("covered", False))
            by = row.get("covered_by", {}) if isinstance(row.get("covered_by"), dict) else {}
            atheris_hit = bool(by.get("atheris", False))
            hypothesis_hit = bool(by.get("hypothesis", False))
            marker = "✅" if covered else "❌"
            lines.append(
                f"- {marker} Line {ln}: covered={covered} (atheris={atheris_hit}, hypothesis={hypothesis_hit})"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_suite_coverage_answer(result: Dict[str, Any]) -> str:
        source_file = str(result.get("source_file", "<unknown source>"))
        reports = result.get("reports", {}) if isinstance(result.get("reports"), dict) else {}
        atheris = reports.get("atheris", {}) if isinstance(reports.get("atheris"), dict) else {}
        hypothesis = reports.get("hypothesis", {}) if isinstance(reports.get("hypothesis"), dict) else {}
        atheris_summary = atheris.get("summary", {}) if isinstance(atheris.get("summary"), dict) else {}
        hypothesis_summary = hypothesis.get("summary", {}) if isinstance(hypothesis.get("summary"), dict) else {}
        combined = result.get("combined", {}) if isinstance(result.get("combined"), dict) else {}

        return "\n".join(
            [
                "Test Suite Coverage Summary",
                f"Source: {source_file}",
                "",
                "Atheris report:",
                f"- Covered lines: {atheris_summary.get('covered_lines', 0)} / {atheris_summary.get('num_statements', 0)}",
                f"- Coverage: {atheris_summary.get('percent_covered_display', '0')}%",
                "",
                "Hypothesis report:",
                f"- Covered lines: {hypothesis_summary.get('covered_lines', 0)} / {hypothesis_summary.get('num_statements', 0)}",
                f"- Coverage: {hypothesis_summary.get('percent_covered_display', '0')}%",
                "",
                "Combined (union of executed lines):",
                f"- Covered lines: {combined.get('covered_lines', 0)} / {combined.get('num_statements', 0)}",
                f"- Coverage: {combined.get('percent_covered_display', '0')}%",
            ]
        )

    def are_lines_covered_by_tests(self, lines: List[int], source_file: Optional[str] = None) -> Dict[str, Any]:
        target = (source_file or self.default_source or "course_management_system.py").strip() or "course_management_system.py"
        inspector = CoverageReportInspector(target)
        result = inspector.lines_covered(self._normalize_lines_arg(lines))
        result["mode"] = "coverage-report"
        result["query_type"] = QueryType.LINES_COVERED_BY_TESTS.value
        result["answer"] = self._format_lines_coverage_answer(result)
        return result

    def get_test_suite_coverage(self, source_file: Optional[str] = None) -> Dict[str, Any]:
        target = (source_file or self.default_source or "course_management_system.py").strip() or "course_management_system.py"
        inspector = CoverageReportInspector(target)
        result = inspector.suite_coverage()
        result["mode"] = "coverage-report"
        result["query_type"] = QueryType.TEST_COVERAGE_SUMMARY.value
        result["answer"] = self._format_suite_coverage_answer(result)
        return result

    @staticmethod
    def _normalize_line_numbers(value: Any) -> List[int]:
        if not isinstance(value, list):
            return []
        lines: List[int] = []
        for item in value:
            if isinstance(item, int) and item > 0:
                lines.append(item)
            elif isinstance(item, str):
                text = item.strip()
                if text.isdigit():
                    num = int(text)
                    if num > 0:
                        lines.append(num)
        # keep stable order, remove duplicates
        unique: List[int] = []
        seen: Set[int] = set()
        for ln in lines:
            if ln not in seen:
                seen.add(ln)
                unique.append(ln)
        return unique

    def _sanitize_related_lines(self, lines: List[int]) -> List[int]:
        """Drop obvious placeholder line numbers and out-of-range values."""
        if not lines:
            return []

        try:
            source_line_count = len(Path(self.default_source).read_text(encoding="utf-8").splitlines())
        except OSError:
            source_line_count = 0

        sanitized = [ln for ln in lines if ln > 0 and (source_line_count == 0 or ln <= source_line_count)]

        # Heuristic: common placeholder examples that may leak from prompt templates.
        if sanitized == [12, 13]:
            return []

        return sanitized

    def _build_ai_user_prompt(self, natural_language_query: str) -> str:
        source_text = self._get_source_for_ai()
        return (
            "User query:\n"
            f"{natural_language_query}\n\n"
            f"Source file: {self.default_source}\n"
            "Source code with explicit 1-based line numbers (possibly truncated):\n"
            "-----BEGIN SOURCE-----\n"
            f"{source_text}\n"
            "-----END SOURCE-----\n"
        )

    def get_ai_info(self, query_placeholder: str = "<QUERY>", source_placeholder: str = "<SOURCE_CODE>") -> Dict[str, Any]:
        """Returns AI runtime metadata and prompt templates for GUI/debug display."""
        client = self.ai_client
        backend = "disabled"
        model = "-"
        base_url = "-"

        if client is not None:
            backend = type(client).__name__
            model = getattr(client, "model", "-")
            base_url = getattr(client, "base_url", "-")

        user_prompt_template = (
            "User query:\n"
            f"{query_placeholder}\n\n"
            f"Source file: {self.default_source}\n"
            "Source code with explicit 1-based line numbers (possibly truncated):\n"
            "-----BEGIN SOURCE-----\n"
            f"{source_placeholder}\n"
            "-----END SOURCE-----\n"
        )

        return {
            "ai_enabled": client is not None,
            "backend": backend,
            "model": model,
            "base_url": base_url,
            "router_system_prompt": self._build_ai_router_prompt(),
            "router_user_prompt_template": user_prompt_template,
        }

    def _get_source_for_ai(self) -> str:
        try:
            lines = Path(self.default_source).read_text(encoding="utf-8").splitlines()
        except OSError:
            return "<source unavailable>"

        rendered: List[str] = []
        used_chars = 0
        last_line_no = 0

        for idx, line in enumerate(lines, start=1):
            entry = f"{idx:4d}: {line}\n"
            if rendered and used_chars + len(entry) > self.ai_source_max_chars:
                break
            rendered.append(entry)
            used_chars += len(entry)
            last_line_no = idx

        if not rendered:
            return "<empty source>"

        out = "".join(rendered).rstrip("\n")
        if last_line_no < len(lines):
            out += f"\n...<truncated after line {last_line_no} of {len(lines)}>"
        return out

    @staticmethod
    def _parse_ai_json(raw: str) -> Optional[Dict[str, Any]]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    def _discover_backend_methods(self) -> Set[str]:
        if self.backend is None:
            return set()
        names: Set[str] = set()
        for name in dir(self.backend):
            if name.startswith("_"):
                continue
            attr = getattr(self.backend, name)
            if callable(attr):
                names.add(name)
        return names

    def _invoke_flexible_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name in self.tool_registry:
            fn = self.tool_registry[tool_name]
            try:
                result = fn(**arguments)
            except TypeError as exc:
                return {
                    "error": f"Tool '{tool_name}' argument mismatch.",
                    "detail": str(exc),
                    "arguments": arguments,
                }
            return {
                "mode": "ai-tool-call",
                "tool_name": tool_name,
                "result": result,
            }

        if self.backend is not None and hasattr(self.backend, tool_name):
            fn = getattr(self.backend, tool_name)
            if callable(fn):
                try:
                    result = fn(**arguments)
                except TypeError as exc:
                    return {
                        "error": f"Backend method '{tool_name}' argument mismatch.",
                        "detail": str(exc),
                        "arguments": arguments,
                    }
                return {
                    "mode": "ai-tool-call",
                    "tool_name": tool_name,
                    "result": result,
                }

        return {
            "error": f"Tool '{tool_name}' is not wired yet.",
            "available_tools": sorted(set(self.tool_registry.keys()) | self._discover_backend_methods()),
            "arguments": arguments,
        }

    def _dispatch_backend(self, command: QueryCommand) -> Dict[str, Any]:
        if command.query_type == QueryType.DEAD_CODE:
            return self.backend.has_dead_code(command.source_file)

        if command.query_type == QueryType.VARS_DEFINED:
            assert command.function_name is not None
            return self.backend.variables_defined(command.source_file, command.function_name)

        if command.query_type == QueryType.VAR_LIVE_AT_POINT:
            assert command.function_name is not None
            assert command.variable_name is not None
            assert command.line is not None
            return self.backend.is_variable_live(
                command.source_file,
                command.function_name,
                command.variable_name,
                command.line,
            )

        if command.query_type == QueryType.CALLEES:
            assert command.function_name is not None
            return self.backend.functions_called_by(command.source_file, command.function_name)

        if command.query_type == QueryType.TRANSITIVE_CALL_CHAIN:
            assert command.function_name is not None
            return self.backend.transitive_call_chain(command.source_file, command.function_name)

        if command.query_type == QueryType.HOTSPOTS:
            return self.backend.hotspots(command.source_file, command.top_k)

        return {"error": f"Unsupported query type: {command.query_type}"}

    def _run_fallback(self, command: QueryCommand) -> Dict[str, Any]:
        if command.query_type == QueryType.LINES_COVERED_BY_TESTS:
            return self.are_lines_covered_by_tests(lines=command.lines or [], source_file=command.source_file)

        if command.query_type == QueryType.TEST_COVERAGE_SUMMARY:
            return self.get_test_suite_coverage(source_file=command.source_file)

        inspector = SourceInspector(command.source_file)

        if command.query_type == QueryType.DEAD_CODE:
            return inspector.has_dead_code()

        if command.query_type == QueryType.VARS_DEFINED:
            assert command.function_name is not None
            return {
                "function": command.function_name,
                "defined_variables": inspector.variables_defined(command.function_name),
            }

        if command.query_type == QueryType.VAR_LIVE_AT_POINT:
            assert command.function_name is not None
            assert command.variable_name is not None
            assert command.line is not None
            return inspector.is_variable_live(command.function_name, command.variable_name, command.line)

        if command.query_type == QueryType.CALLEES:
            assert command.function_name is not None
            return {
                "function": command.function_name,
                "callees": inspector.functions_called_by(command.function_name),
            }

        if command.query_type == QueryType.TRANSITIVE_CALL_CHAIN:
            assert command.function_name is not None
            return {
                "function": command.function_name,
                "transitive_callees": inspector.transitive_call_chain(command.function_name),
            }

        if command.query_type == QueryType.HOTSPOTS:
            return {"hotspots": inspector.hotspots(command.top_k)}

        return {"error": f"Unsupported query type: {command.query_type}"}

    def _fallback_or_reject(self, natural_language_query: str) -> Dict[str, Any]:
        # Best effort: if user asks for parse tree-ish info we can still provide function list.
        low = natural_language_query.lower()
        if "covered by tests" in low or ("line" in low and "coverage" in low):
            lines = self.mapper._extract_line_numbers(natural_language_query)
            return self.are_lines_covered_by_tests(lines=lines, source_file=self.default_source)

        if "coverage of the test suite" in low or "test suite coverage" in low:
            return self.get_test_suite_coverage(source_file=self.default_source)

        if "list functions" in low or "what functions" in low:
            inspector = SourceInspector(self.default_source)
            return {
                "fallback_answer": "Functions discovered in source file.",
                "functions": sorted(inspector.functions.keys()),
            }

        return {
            "error": "Unsupported query format.",
            "supported_types": [qt.value for qt in QueryType],
            "message": (
                "This interface only supports 8 predefined query families. "
                "Please rephrase your question to one of them."
            ),
        }


def _pretty_print(result: Dict[str, Any]) -> None:
    for key, value in result.items():
        print(f"{key}: {value}")


def run_cli() -> None:
    """Simple interactive CLI for demo usage."""
    qi = QueryInterface(
        backend=None,
        default_source="course_management_system.py",
        ai_client=make_ai_client_from_env(),
    )
    if qi.ai_client is not None:
        print("Query Interface ready (AI router enabled via environment config).")
    else:
        print("Query Interface ready (fallback mode, no AI key found).")
    print("Ask questions in natural language. Type 'exit' to quit.")

    while True:
        user_q = input("\n> ").strip()
        if user_q.lower() in {"exit", "quit"}:
            print("Bye!")
            return
        if not user_q:
            continue

        result = qi.execute(user_q)
        _pretty_print(result)


if __name__ == "__main__":
    run_cli()
