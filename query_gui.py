"""Simple GUI for the query system.

Features:
- Ask natural-language queries.
- Show structured result fields (mode/query_type/can_answer).
- Show full source code.
- Highlight AI-reported related lines in source view.
"""

from __future__ import annotations

import ast
import json
import keyword
import io
import os
import re
import sys
import tokenize
import token
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
except ModuleNotFoundError:  # pragma: no cover - depends on local OS packages
    tk = None
    ttk = None
    ScrolledText = Any

from query_interface import QueryInterface, make_ai_client_from_env
from query_interface import run_cli as run_query_cli


BaseTk = tk.Tk if tk is not None else object

EXAMPLE_QUERIES: List[str] = [
    "Are there any unreachable functions in the program?",
    "Inside parse_object, which variables are defined?",
    "In function parse_string, is esc live at line 224?",
    "Does parse call parse_value?",
    "Give me the full call chain of run_tests.",
    "Show top 5 hotspots in the program.",
    "Are lines 192-210 covered by tests?",
    "What is the coverage of the test suite?",
    "Compute the static slice w.r.t. criterion (L184, int_part).",
    "Which line(s) is line 288 control dependent on?",
    "Which line(s) is line 188 data dependent on?",
]

# Approximate pricing assumptions (USD / 1M tokens). These may change over time.
MODEL_PRICING: List[Dict[str, Any]] = [
    {"model": "gpt-4o-mini", "input_per_1m": 0.15, "output_per_1m": 0.60},
    {"model": "gpt-4.1-nano", "input_per_1m": 0.10, "output_per_1m": 0.40},
    {"model": "gpt-4.1-mini", "input_per_1m": 0.40, "output_per_1m": 1.60},
    {"model": "gpt-4o", "input_per_1m": 5.00, "output_per_1m": 15.00},
    {"model": "gpt-5.4-nano", "input_per_1m": 0.12, "output_per_1m": 0.48},
    {"model": "gpt-5.4-mini", "input_per_1m": 0.45, "output_per_1m": 1.80},
    {"model": "gpt-5.4", "input_per_1m": 6.00, "output_per_1m": 18.00},
]


class QuerySystemGUI(BaseTk):
    def __init__(self) -> None:
        if tk is None or ttk is None:
            raise RuntimeError(
                "tkinter is not available in this Python environment. "
                "Install OS tkinter support (e.g., python3-tk) and try again."
            )
        super().__init__()
        self.title("Query System GUI")
        self.geometry("1400x900")
        self.minsize(1100, 700)

        self.source_file_var = tk.StringVar(value="course_management_system.py")
        self.query_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="-")
        self.query_type_var = tk.StringVar(value="-")
        self.can_answer_var = tk.StringVar(value="-")
        self.status_var = tk.StringVar(value="Ready")

        self.query_interface = QueryInterface(
            backend=None,
            default_source=self.source_file_var.get(),
            ai_client=make_ai_client_from_env(),
        )

        self._configure_styles()
        self._build_layout()
        self._load_source()
        self.bind_all("<Control-Return>", lambda _e: self._run_query())
        self.bind_all("<Control-l>", lambda _e: self._focus_query_box())

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("TFrame", padding=0)
        style.configure("Card.TLabelframe", padding=8)
        style.configure("Card.TLabelframe.Label", font=("TkDefaultFont", 12, "bold"))
        style.configure("Status.TLabel", padding=(8, 4))
        style.configure("SummaryKey.TLabel", font=("TkDefaultFont", 12, "bold"))
        style.configure("SummaryValue.TLabel", font=("TkDefaultFont", 12))

    def _build_layout(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(top, text="Source file:").grid(row=0, column=0, sticky="w")
        src_entry = ttk.Entry(top, textvariable=self.source_file_var, width=55)
        src_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))

        ttk.Button(top, text="Reload Source", command=self._reload_source).grid(row=0, column=2, padx=(0, 8))
        self.ai_status_label = ttk.Label(top, text=self._ai_status_text())
        self.ai_status_label.grid(row=0, column=3, sticky="e")
        ttk.Button(top, text="AI Info", command=self._open_ai_info_dialog).grid(row=0, column=4, padx=(8, 0))

        ttk.Label(top, text="Query:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        query_entry = ttk.Entry(top, textvariable=self.query_var)
        query_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(6, 6), pady=(8, 0))
        query_entry.bind("<Return>", lambda _e: self._run_query())
        self.query_entry = query_entry
        ttk.Button(top, text="Run Query", command=self._run_query).grid(row=1, column=3, sticky="e", pady=(8, 0))
        ttk.Button(top, text="Example Queries", command=self._open_example_queries_dialog).grid(row=1, column=4, sticky="e", padx=(8, 0), pady=(8, 0))
        ttk.Button(top, text="Clear", command=self._clear_outputs).grid(row=1, column=5, sticky="e", padx=(8, 0), pady=(8, 0))

        top.columnconfigure(1, weight=1)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=2)

        meta = ttk.LabelFrame(left, text="Result Summary", style="Card.TLabelframe")
        meta.pack(fill=tk.X, pady=(0, 8))

        self._add_meta_row(meta, 0, "mode", self.mode_var)
        self._add_meta_row(meta, 1, "query_type", self.query_type_var)
        self._add_meta_row(meta, 2, "can_answer", self.can_answer_var)

        ans_frame = ttk.LabelFrame(left, text="Answer / Result", style="Card.TLabelframe")
        ans_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.answer_text = ScrolledText(ans_frame, wrap=tk.WORD, height=20)
        self.answer_text.pack(fill=tk.BOTH, expand=True)
        self.answer_text.configure(font=("Consolas", 11) if sys.platform.startswith("win") else ("Menlo", 12) if sys.platform == "darwin" else ("DejaVu Sans Mono", 11), padx=8, pady=8)

        src_frame = ttk.LabelFrame(right, text="Source Code", style="Card.TLabelframe")
        src_frame.pack(fill=tk.BOTH, expand=True)
        self.source_text = ScrolledText(src_frame, wrap=tk.NONE)
        self.source_text.pack(fill=tk.BOTH, expand=True)
        self.source_text.configure(font=("Consolas", 11) if sys.platform.startswith("win") else ("Menlo", 12) if sys.platform == "darwin" else ("DejaVu Sans Mono", 11), padx=8, pady=8)

        # Syntax + query highlight tags.
        # VS Code Dark+ inspired palette.
        self.source_text.tag_configure("py_keyword", foreground="#C586C0")
        self.source_text.tag_configure("py_control", foreground="#569CD6")
        self.source_text.tag_configure("py_string", foreground="#CE9178")
        self.source_text.tag_configure("py_comment", foreground="#6A9955")
        self.source_text.tag_configure("py_defname", foreground="#DCDCAA")
        self.source_text.tag_configure("py_decorator", foreground="#C586C0")
        self.source_text.tag_configure("py_param", foreground="#9CDCFE")
        self.source_text.tag_configure("py_variable", foreground="#9CDCFE")
        self.source_text.tag_configure("py_call", foreground="#D7BA7D")
        self.source_text.tag_configure("line_number", foreground="#858585")
        self.source_text.tag_configure("line_highlight", background="#264F78", foreground="#FFFFFF")
        self.source_text.tag_configure("line_covered", background="#1E4D2B", foreground="#FFFFFF")
        self.source_text.tag_configure("line_not_covered", background="#5A1E24", foreground="#FFFFFF")

        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w", style="Status.TLabel")
        status_bar.pack(fill=tk.X, padx=10, pady=(0, 8))

    @staticmethod
    def _add_meta_row(parent: Any, row: int, label: str, var: Any) -> None:
        ttk.Label(parent, text=f"{label}:", style="SummaryKey.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(parent, textvariable=var, style="SummaryValue.TLabel").grid(row=row, column=1, sticky="w", padx=6, pady=4)

    def _ai_status_text(self) -> str:
        return "AI: enabled" if self.query_interface.ai_client is not None else "AI: disabled (fallback only)"

    def _reload_source(self) -> None:
        self.query_interface.default_source = self.source_file_var.get().strip() or "course_management_system.py"
        self._load_source()

    def _load_source(self) -> None:
        src = self.source_file_var.get().strip() or "course_management_system.py"
        self.source_text.configure(state=tk.NORMAL)
        self.source_text.delete("1.0", tk.END)
        self.source_text.tag_remove("line_highlight", "1.0", tk.END)

        raw_content = ""
        try:
            raw_content = Path(src).read_text(encoding="utf-8")
            content = self._render_source_with_line_numbers(raw_content)
        except OSError as exc:
            content = f"Unable to load source file '{src}': {exc}"

        self.source_text.insert("1.0", content)
        self._apply_python_syntax_highlighting(raw_content)
        self.source_text.tag_raise("line_highlight")
        self.source_text.configure(state=tk.DISABLED)
        self._set_status(f"Loaded source: {src}")

    @staticmethod
    def _render_source_with_line_numbers(source: str) -> str:
        lines = source.splitlines()
        if not lines:
            return ""
        width = max(4, len(str(len(lines))))
        return "\n".join(f"{idx:>{width}} | {line}" for idx, line in enumerate(lines, start=1))

    def _open_example_queries_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Example Queries")
        dialog.geometry("1050x560")
        dialog.transient(self)

        container = ttk.Frame(dialog)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(container, text="Click Apply to place a query into the input box.").pack(anchor="w", pady=(0, 8))

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for idx, q in enumerate(EXAMPLE_QUERIES, start=1):
            row = ttk.Frame(scroll_frame)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=f"{idx:02d}.", width=4).pack(side=tk.LEFT)
            ttk.Label(row, text=q).pack(side=tk.LEFT, fill=tk.X, expand=True)
            btns = ttk.Frame(row)
            btns.pack(side=tk.RIGHT)
            ttk.Button(btns, text="Apply", command=lambda query=q: self._apply_example_query(query, dialog, run=False)).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Button(btns, text="Apply + Run", command=lambda query=q: self._apply_example_query(query, dialog, run=True)).pack(side=tk.LEFT)

    def _apply_example_query(self, query: str, dialog: Any, run: bool = False) -> None:
        self.query_var.set(query)
        if run:
            self._run_query()
        try:
            dialog.destroy()
        except Exception:
            pass

    def _open_ai_info_dialog(self) -> None:
        info = self.query_interface.get_ai_info()

        dialog = tk.Toplevel(self)
        dialog.title("AI Info")
        dialog.geometry("1100x760")
        dialog.transient(self)

        root = ttk.Frame(dialog)
        root.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        summary = (
            f"AI Enabled: {info.get('ai_enabled')}\n"
            f"Backend: {info.get('backend')}\n"
            f"Model: {info.get('model')}\n"
            f"Base URL: {info.get('base_url')}"
        )
        ttk.Label(root, text=summary, justify=tk.LEFT).pack(anchor="w", pady=(0, 8))

        model_frame = ttk.LabelFrame(root, text="AI Model")
        model_frame.pack(fill=tk.X, pady=(0, 8))

        input_tokens = self._estimate_input_tokens_for_query(self.query_var.get().strip() or "<QUERY>")
        assumed_output_tokens = 180
        ttk.Label(
            model_frame,
            text=(
                "Estimated with current prompt size. "
                f"Assuming ~{input_tokens} input tokens and ~{assumed_output_tokens} output tokens/query."
            ),
            justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 4))

        model_options: List[str] = []
        option_to_model: Dict[str, str] = {}
        current_model = str(info.get("model", ""))
        current_selection = ""

        for item in MODEL_PRICING:
            model_name = item["model"]
            cost = self._estimate_cost_per_query(
                input_tokens=input_tokens,
                output_tokens=assumed_output_tokens,
                input_price_per_1m=float(item["input_per_1m"]),
                output_price_per_1m=float(item["output_per_1m"]),
            )
            label = f"{model_name}  (~${cost:.6f}/query)"
            model_options.append(label)
            option_to_model[label] = model_name
            if model_name == current_model:
                current_selection = label

        selected_model_label = tk.StringVar(value=current_selection or (model_options[0] if model_options else ""))
        model_combo = ttk.Combobox(model_frame, textvariable=selected_model_label, values=model_options, state="readonly", width=55)
        model_combo.grid(row=1, column=0, sticky="w", padx=8, pady=(2, 6))

        apply_status_var = tk.StringVar(value="")

        def apply_model() -> None:
            picked = selected_model_label.get().strip()
            target_model = option_to_model.get(picked)
            if not target_model:
                apply_status_var.set("No model selected.")
                return

            client = self.query_interface.ai_client
            if client is None:
                apply_status_var.set("AI client is disabled (no API key / backend).")
                return

            if hasattr(client, "model"):
                setattr(client, "model", target_model)
                os.environ["OPENAI_MODEL"] = target_model
                apply_status_var.set(f"Applied model: {target_model}")
                self.ai_status_label.configure(text=self._ai_status_text())
            else:
                apply_status_var.set("Current AI backend does not support runtime model updates.")

        ttk.Button(model_frame, text="Apply Model", command=apply_model).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(2, 6))
        ttk.Label(model_frame, textvariable=apply_status_var).grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(2, 6))

        ttk.Label(
            model_frame,
            text="Note: prices are rough estimates and may differ from current provider billing.",
            justify=tk.LEFT,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8))

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, pady=(0, 6))

        def copy_prompt() -> None:
            payload = (
                "[System Prompt]\n"
                + str(info.get("router_system_prompt", ""))
                + "\n\n[User Prompt Template]\n"
                + str(info.get("router_user_prompt_template", ""))
            )
            self.clipboard_clear()
            self.clipboard_append(payload)
            self._set_status("Copied prompt info to clipboard.")

        ttk.Button(actions, text="Copy Prompt", command=copy_prompt).pack(side=tk.LEFT)

        prompt_box = ScrolledText(root, wrap=tk.WORD)
        prompt_box.pack(fill=tk.BOTH, expand=True)
        prompt_box.insert(
            "1.0",
            "[System Prompt]\n"
            + str(info.get("router_system_prompt", ""))
            + "\n\n[User Prompt Template]\n"
            + str(info.get("router_user_prompt_template", "")),
        )
        prompt_box.configure(state=tk.DISABLED)

    def _estimate_input_tokens_for_query(self, query_text: str) -> int:
        # Approximation: 1 token ~= 4 chars.
        system_prompt = self.query_interface._build_ai_router_prompt()
        user_prompt = self.query_interface._build_ai_user_prompt(query_text)
        return max(1, int((len(system_prompt) + len(user_prompt)) / 4))

    @staticmethod
    def _estimate_cost_per_query(
        input_tokens: int,
        output_tokens: int,
        input_price_per_1m: float,
        output_price_per_1m: float,
    ) -> float:
        return (input_tokens / 1_000_000.0) * input_price_per_1m + (output_tokens / 1_000_000.0) * output_price_per_1m

    def _run_query(self) -> None:
        query = self.query_var.get().strip()
        if not query:
            self._set_status("Query is empty.")
            return

        self.query_interface.default_source = self.source_file_var.get().strip() or "course_management_system.py"
        self._set_status("Running query...")
        result = self.query_interface.execute(query)
        self._render_result(result)
        self._set_status(f"Query finished at {datetime.now().strftime('%H:%M:%S')}")

    def _render_result(self, result: Dict[str, Any]) -> None:
        mode = str(result.get("mode", "-"))
        query_type = str(result.get("query_type", "-"))

        can_answer_value = result.get("can_answer")
        can_answer = "no" if can_answer_value is False else "yes"

        self.mode_var.set(mode)
        self.query_type_var.set(query_type)
        self.can_answer_var.set(can_answer)

        answer_payload = self._format_answer_payload(result)
        self._set_text(self.answer_text, answer_payload)

        coverage_by_line = self._extract_coverage_by_line(result)
        related_lines = self._extract_related_lines(result)
        if not related_lines and coverage_by_line:
            related_lines = sorted(coverage_by_line.keys())

        self._highlight_source_lines(related_lines, coverage_by_line=coverage_by_line)

    @staticmethod
    def _format_answer_payload(result: Dict[str, Any]) -> str:
        if "answer" in result and isinstance(result.get("answer"), str):
            return result["answer"]

        # AI tool-call wrapper often nests the human-readable answer inside result.answer
        # shape: {"mode":"ai-tool-call", "tool_name":"...", "result": {"answer": "...", ...}}
        nested = result.get("result")
        if isinstance(nested, dict):
            nested_answer = nested.get("answer")
            if isinstance(nested_answer, str) and nested_answer.strip():
                return nested_answer

        # Keep the answer box focused on the answer-like payload only.
        filtered = {
            k: v
            for k, v in result.items()
            if k not in {"mode", "query_type", "can_answer", "related_lines"}
        }
        return json.dumps(filtered, indent=2, ensure_ascii=False)

    @staticmethod
    def _extract_related_lines(result: Dict[str, Any]) -> List[int]:
        raw = result.get("related_lines", [])
        if not isinstance(raw, list):
            return []
        out: List[int] = []
        for x in raw:
            if isinstance(x, int) and x > 0:
                out.append(x)
        return out

    @staticmethod
    def _extract_coverage_by_line(result: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        # Supports both direct coverage payload and AI tool-call wrapper payload.
        payload = result
        nested = result.get("result")
        if isinstance(nested, dict) and isinstance(nested.get("per_line"), list):
            payload = nested

        per_line = payload.get("per_line", [])
        if not isinstance(per_line, list):
            return {}

        out: Dict[int, Dict[str, Any]] = {}
        for row in per_line:
            if not isinstance(row, dict):
                continue
            ln = row.get("line")
            if not isinstance(ln, int) or ln <= 0:
                continue
            hits = row.get("coverage_hits")
            total = row.get("coverage_total")
            covered = bool(row.get("covered", False))
            by = row.get("covered_by", {}) if isinstance(row.get("covered_by"), dict) else {}

            if not isinstance(hits, int) or not isinstance(total, int) or total <= 0:
                hits = sum(1 for _k, v in by.items() if bool(v))
                total = max(1, len(by))

            rate = row.get("coverage_rate")
            if not isinstance(rate, (int, float)):
                rate = (hits / total) * 100.0

            out[ln] = {
                "covered": covered,
                "hits": int(hits),
                "total": int(total),
                "rate": float(rate),
                "coverage_by_tool": row.get("coverage_by_tool", {}) if isinstance(row.get("coverage_by_tool"), dict) else {},
            }
        return out

    @staticmethod
    def _is_blank_or_comment_source_line(line_text: str) -> bool:
        sep = line_text.find(" | ")
        src = line_text[sep + 3 :] if sep >= 0 else line_text
        stripped = src.strip()
        if not stripped:
            return True
        return stripped.startswith("#")

    @staticmethod
    def _set_text(widget: Any, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    def _highlight_source_lines(self, lines: List[int], coverage_by_line: Optional[Dict[int, Dict[str, Any]]] = None) -> None:
        self.source_text.configure(state=tk.NORMAL)
        self.source_text.tag_remove("line_highlight", "1.0", tk.END)
        self.source_text.tag_remove("line_covered", "1.0", tk.END)
        self.source_text.tag_remove("line_not_covered", "1.0", tk.END)

        coverage_by_line = coverage_by_line or {}

        # determine max line in widget to avoid invalid ranges
        end_index = self.source_text.index("end-1c")
        max_line = int(end_index.split(".")[0]) if end_index else 1

        valid_lines = [ln for ln in lines if 1 <= ln <= max_line]
        visible_lines = [
            ln
            for ln in valid_lines
            if not self._is_blank_or_comment_source_line(self.source_text.get(f"{ln}.0", f"{ln}.0 lineend"))
        ]

        for ln in visible_lines:
            start = f"{ln}.0"
            end = f"{ln}.0 lineend"
            info = coverage_by_line.get(ln)
            if info is None:
                self.source_text.tag_add("line_highlight", start, end)
                continue

            covered = bool(info.get("covered", False))
            line_tag = "line_covered" if covered else "line_not_covered"
            self.source_text.tag_add(line_tag, start, end)

        if lines:
            first = min(ln for ln in lines if ln > 0)
            self.source_text.see(f"{first}.0")

        self.source_text.tag_raise("line_covered")
        self.source_text.tag_raise("line_not_covered")
        self.source_text.tag_raise("line_highlight")
        self.source_text.configure(state=tk.DISABLED)

    def _clear_outputs(self) -> None:
        self.mode_var.set("-")
        self.query_type_var.set("-")
        self.can_answer_var.set("-")
        self._set_text(self.answer_text, "")
        self._highlight_source_lines([], coverage_by_line={})
        self._set_status("Cleared outputs.")

    def _focus_query_box(self) -> None:
        try:
            self.query_entry.focus_set()
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _apply_python_syntax_highlighting(self, source: str) -> None:
        # Reset syntax tags.
        for tag in (
            "py_keyword",
            "py_control",
            "py_string",
            "py_comment",
            "py_defname",
            "py_decorator",
            "py_param",
            "py_variable",
            "py_call",
            "line_number",
        ):
            self.source_text.tag_remove(tag, "1.0", tk.END)

        source_lines = source.splitlines()
        line_count = len(source_lines)
        if line_count == 0:
            line_count = 1
        gutter_width = max(4, len(str(line_count)))
        gutter_len = gutter_width + 3  # "<line_no> | "

        def widget_index(line_no: int, raw_col: int) -> str:
            safe_line = max(1, line_no)
            safe_col = max(0, raw_col)
            return f"{safe_line}.{gutter_len + safe_col}"

        def add_span(tag: str, sline: int, scol: int, eline: int, ecol: int) -> None:
            if sline <= 0 or eline <= 0:
                return
            if (eline, ecol) < (sline, scol):
                return
            self.source_text.tag_add(tag, widget_index(sline, scol), widget_index(eline, ecol))

        control_keywords = {"class", "def", "if", "elif", "else", "for", "while", "try", "except", "finally", "with", "return"}

        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
            expect_defname = False
            for tok in tokens:
                tok_type = tok.type
                tok_text = tok.string
                (sline, scol) = tok.start
                (eline, ecol) = tok.end

                if tok_type == token.NAME:
                    if tok_text in keyword.kwlist:
                        add_span("py_keyword", sline, scol, eline, ecol)
                    if tok_text in control_keywords:
                        add_span("py_control", sline, scol, eline, ecol)
                    if expect_defname:
                        add_span("py_defname", sline, scol, eline, ecol)
                        expect_defname = False
                    if tok_text in {"def", "class"}:
                        expect_defname = True
                    continue

                if tok_type == token.STRING:
                    add_span("py_string", sline, scol, eline, ecol)
                elif tok_type == tokenize.COMMENT:
                    add_span("py_comment", sline, scol, eline, ecol)

                if tok_type not in {tokenize.NL, token.NEWLINE, token.INDENT, token.DEDENT}:
                    expect_defname = False
        except tokenize.TokenError:
            # If source has temporary syntax issues while editing, skip token-based tags.
            pass

        # Decorators: highlight full decorator lines (e.g., @dataclass, @staticmethod).
        for line_no, line_text in enumerate(source_lines, start=1):
            match = re.match(r"^\s*@[^\n\r]*", line_text)
            if not match:
                continue
            start_col = match.start()
            end_col = match.end()
            add_span("py_decorator", line_no, start_col, line_no, end_col)

        # Add richer semantic tags from AST: parameters, variables, and function calls.
        try:
            tree = ast.parse(source)

            # Build parent links so we can determine enclosing function scope.
            parent: Dict[ast.AST, ast.AST] = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parent[child] = node

            def _enclosing_callable(node: ast.AST) -> Any:
                cur: Optional[ast.AST] = node
                while cur is not None:
                    if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                        return cur
                    cur = parent.get(cur)
                return None

            param_names_by_callable: Dict[ast.AST, Set[str]] = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    args_obj = node.args
                    names: Set[str] = set(arg.arg for arg in getattr(args_obj, "args", []))
                    names |= set(arg.arg for arg in getattr(args_obj, "kwonlyargs", []))
                    posonly = getattr(args_obj, "posonlyargs", [])
                    names |= set(arg.arg for arg in posonly)
                    if getattr(args_obj, "vararg", None):
                        names.add(args_obj.vararg.arg)
                    if getattr(args_obj, "kwarg", None):
                        names.add(args_obj.kwarg.arg)
                    param_names_by_callable[node] = names

            for node in ast.walk(tree):
                if isinstance(node, ast.arg):
                    if hasattr(node, "lineno") and hasattr(node, "col_offset"):
                        start_col = int(node.col_offset)
                        end_col = start_col + len(node.arg)
                        add_span("py_param", int(node.lineno), start_col, int(node.lineno), end_col)
                    continue

                if isinstance(node, ast.Name):
                    # Keep common receiver names uncolored as variables.
                    if node.id in {"self", "cls"}:
                        continue

                    tag = "py_variable"
                    scope = _enclosing_callable(node)
                    if scope is not None and node.id in param_names_by_callable.get(scope, set()):
                        tag = "py_param"

                    add_span(
                        tag,
                        int(node.lineno),
                        int(node.col_offset),
                        int(getattr(node, "end_lineno", node.lineno)),
                        int(getattr(node, "end_col_offset", node.col_offset + len(node.id))),
                    )
                    continue

                if isinstance(node, ast.Call):
                    func_node = node.func
                    if isinstance(func_node, ast.Name):
                        add_span(
                            "py_call",
                            int(func_node.lineno),
                            int(func_node.col_offset),
                            int(getattr(func_node, "end_lineno", func_node.lineno)),
                            int(getattr(func_node, "end_col_offset", func_node.col_offset + len(func_node.id))),
                        )
                    elif isinstance(func_node, ast.Attribute):
                        # Highlight only the called attribute (method/function name), not the object receiver.
                        end_line = int(getattr(func_node, "end_lineno", func_node.lineno))
                        end_col = int(getattr(func_node, "end_col_offset", func_node.col_offset))
                        attr_len = len(func_node.attr)
                        start_col = max(int(func_node.col_offset), end_col - attr_len)
                        add_span("py_call", end_line, start_col, end_line, end_col)
        except SyntaxError:
            # Skip AST-based semantic tags if source is temporarily syntactically invalid.
            pass

        # Keep the line-number gutter style fixed and free from syntax tags.
        # This prevents multiline string/comment tags from bleeding into line numbers.
        widget_line_count = int(self.source_text.index("end-1c").split(".")[0])
        syntax_tags = (
            "py_keyword",
            "py_control",
            "py_string",
            "py_comment",
            "py_defname",
            "py_decorator",
            "py_param",
            "py_variable",
            "py_call",
        )
        for ln in range(1, widget_line_count + 1):
            line_text = self.source_text.get(f"{ln}.0", f"{ln}.0 lineend")
            sep_idx = line_text.find(" | ")
            if sep_idx == -1:
                continue
            gutter_end_col = sep_idx + 3
            gutter_start = f"{ln}.0"
            gutter_end = f"{ln}.{gutter_end_col}"
            for tag in syntax_tags:
                self.source_text.tag_remove(tag, gutter_start, gutter_end)
            self.source_text.tag_add("line_number", gutter_start, gutter_end)

        # Keep control and line highlights visible over generic keyword tag.
        self.source_text.tag_raise("line_number")
        self.source_text.tag_raise("py_control")
        self.source_text.tag_raise("py_decorator")
        self.source_text.tag_raise("py_call")
        self.source_text.tag_raise("py_param")
        self.source_text.tag_raise("py_variable")
        self.source_text.tag_raise("line_highlight")


def run_gui() -> None:
    # On many remote Linux servers there is no X/Wayland display.
    # Note: macOS often has no DISPLAY even when GUI is available.
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("No GUI display detected ($DISPLAY is not set). Falling back to CLI mode.")
        run_query_cli()
        return

    try:
        app = QuerySystemGUI()
        app.mainloop()
    except Exception as exc:
        # Graceful fallback for runtime display errors.
        if "no display name" in str(exc).lower() or "$display" in str(exc).lower():
            print("GUI cannot start because no display is available. Falling back to CLI mode.")
            run_query_cli()
            return
        raise


if __name__ == "__main__":
    run_gui()
