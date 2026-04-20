"""Natural-language query interface for static-analysis results.

Scope: supports exactly 6 query families.
Target source (default): json_parser.py
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


@dataclass
class QueryCommand:
    query_type: QueryType
    source_file: str = "json_parser.py"
    function_name: Optional[str] = None
    variable_name: Optional[str] = None
    line: Optional[int] = None
    top_k: int = 5


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

    def map_to_command(self, text: str, default_source: str = "json_parser.py") -> Optional[QueryCommand]:
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

        return None


class QueryInterface:
    """Main orchestration layer for NL query => command => API call => response."""

    def __init__(
        self,
        backend: Optional[QueryBackend] = None,
        default_source: str = "json_parser.py",
        ai_client: Optional[AIClient] = None,
        tool_registry: Optional[Dict[str, Callable[..., Dict[str, Any]]]] = None,
        ai_source_max_chars: int = 40000,
    ):
        self.backend = backend
        self.default_source = default_source
        self.mapper = NLQueryMapper()
        self.ai_client = ai_client
        self.tool_registry = tool_registry or {}
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
            "You are a query router and answerer for static-analysis questions over a Python source file.\n"
            "Return ONLY JSON, no markdown.\n"
            "Allowed JSON formats:\n"
            "1) {\"action\":\"call_local_api\",\"query_type\":\"...\",\"tool_name\":\"...\",\"arguments\":{...}}\n"
            "2) {\"action\":\"answer_from_source\",\"query_type\":\"...\",\"can_answer\":true,\"answer\":\"...\",\"related_lines\":[12,13]}\n"
            "3) {\"action\":\"cannot_answer\",\"query_type\":\"...\",\"reason\":\"...\",\"related_lines\":[...]}\n"
            "4) {\"action\":\"delegate_to_regex\"}\n"
            "Supported query types: q1_dead_code, q2_vars_defined, q3_var_live_at_point, q4_callees, q5_transitive_call_chain, q6_hotspots, other.\n"
            "Decision policy:\n"
            "- If query is one of the six supported types AND a suitable local tool exists, return call_local_api.\n"
            "- If query is one of the six supported types but no suitable local tool exists, inspect source and return answer_from_source or cannot_answer.\n"
            "- If query is not one of the six types, inspect source and return answer_from_source or cannot_answer.\n"
            "- Never invent tool names; choose only from available tools listed below.\n"
            "- For answer_from_source/cannot_answer, include related_lines as the most relevant 1-based source line numbers when possible.\n"
            "Known available tool names right now:\n"
            f"{tool_doc}\n"
            "Important: arguments must be a JSON object with primitive values/arrays/objects only."
        )

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

    def _build_ai_user_prompt(self, natural_language_query: str) -> str:
        source_text = self._get_source_for_ai()
        return (
            "User query:\n"
            f"{natural_language_query}\n\n"
            f"Source file: {self.default_source}\n"
            "Source code (possibly truncated):\n"
            "-----BEGIN SOURCE-----\n"
            f"{source_text}\n"
            "-----END SOURCE-----\n"
        )

    def _get_source_for_ai(self) -> str:
        try:
            text = Path(self.default_source).read_text(encoding="utf-8")
        except OSError:
            return "<source unavailable>"
        if len(text) > self.ai_source_max_chars:
            return text[: self.ai_source_max_chars] + "\n...<truncated>"
        return text

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
                "This interface only supports 6 predefined query families. "
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
        default_source="json_parser.py",
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
