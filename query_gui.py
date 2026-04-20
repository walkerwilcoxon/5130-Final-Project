"""Simple GUI for the query system.

Features:
- Ask natural-language queries.
- Show structured result fields (mode/query_type/can_answer).
- Show full source code.
- Highlight AI-reported related lines in source view.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

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

        self.source_file_var = tk.StringVar(value="json_parser.py")
        self.query_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="-")
        self.query_type_var = tk.StringVar(value="-")
        self.can_answer_var = tk.StringVar(value="-")

        self.query_interface = QueryInterface(
            backend=None,
            default_source=self.source_file_var.get(),
            ai_client=make_ai_client_from_env(),
        )

        self._build_layout()
        self._load_source()

    def _build_layout(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(top, text="Source file:").grid(row=0, column=0, sticky="w")
        src_entry = ttk.Entry(top, textvariable=self.source_file_var, width=55)
        src_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))

        ttk.Button(top, text="Reload Source", command=self._reload_source).grid(row=0, column=2, padx=(0, 8))
        self.ai_status_label = ttk.Label(top, text=self._ai_status_text())
        self.ai_status_label.grid(row=0, column=3, sticky="e")

        ttk.Label(top, text="Query:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        query_entry = ttk.Entry(top, textvariable=self.query_var)
        query_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(6, 6), pady=(8, 0))
        query_entry.bind("<Return>", lambda _e: self._run_query())
        ttk.Button(top, text="Run Query", command=self._run_query).grid(row=1, column=3, sticky="e", pady=(8, 0))

        top.columnconfigure(1, weight=1)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=2)

        meta = ttk.LabelFrame(left, text="Result Summary")
        meta.pack(fill=tk.X, pady=(0, 8))

        self._add_meta_row(meta, 0, "mode", self.mode_var)
        self._add_meta_row(meta, 1, "query_type", self.query_type_var)
        self._add_meta_row(meta, 2, "can_answer", self.can_answer_var)

        ans_frame = ttk.LabelFrame(left, text="Answer / Result")
        ans_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.answer_text = ScrolledText(ans_frame, wrap=tk.WORD, height=20)
        self.answer_text.pack(fill=tk.BOTH, expand=True)

        rel_frame = ttk.LabelFrame(left, text="Related Lines")
        rel_frame.pack(fill=tk.BOTH, expand=True)
        self.related_lines_text = ScrolledText(rel_frame, wrap=tk.NONE, height=10)
        self.related_lines_text.pack(fill=tk.BOTH, expand=True)

        src_frame = ttk.LabelFrame(right, text="Source Code")
        src_frame.pack(fill=tk.BOTH, expand=True)
        self.source_text = ScrolledText(src_frame, wrap=tk.NONE)
        self.source_text.pack(fill=tk.BOTH, expand=True)
        self.source_text.tag_configure("line_highlight", background="#fff2a8")

    @staticmethod
    def _add_meta_row(parent: Any, row: int, label: str, var: Any) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(parent, textvariable=var).grid(row=row, column=1, sticky="w", padx=6, pady=4)

    def _ai_status_text(self) -> str:
        return "AI: enabled" if self.query_interface.ai_client is not None else "AI: disabled (fallback only)"

    def _reload_source(self) -> None:
        self.query_interface.default_source = self.source_file_var.get().strip() or "json_parser.py"
        self._load_source()

    def _load_source(self) -> None:
        src = self.source_file_var.get().strip() or "json_parser.py"
        self.source_text.configure(state=tk.NORMAL)
        self.source_text.delete("1.0", tk.END)
        self.source_text.tag_remove("line_highlight", "1.0", tk.END)

        try:
            content = Path(src).read_text(encoding="utf-8")
        except OSError as exc:
            content = f"Unable to load source file '{src}': {exc}"

        self.source_text.insert("1.0", content)
        self.source_text.configure(state=tk.DISABLED)

    def _run_query(self) -> None:
        query = self.query_var.get().strip()
        if not query:
            return

        self.query_interface.default_source = self.source_file_var.get().strip() or "json_parser.py"
        result = self.query_interface.execute(query)
        self._render_result(result)

    def _render_result(self, result: Dict[str, Any]) -> None:
        mode = str(result.get("mode", "-"))
        query_type = str(result.get("query_type", "-"))

        can_answer_value = result.get("can_answer")
        if can_answer_value is None:
            if "error" in result:
                can_answer = "no"
            else:
                can_answer = "-"
        else:
            can_answer = "yes" if bool(can_answer_value) else "no"

        self.mode_var.set(mode)
        self.query_type_var.set(query_type)
        self.can_answer_var.set(can_answer)

        answer_payload = self._format_answer_payload(result)
        self._set_text(self.answer_text, answer_payload)

        related_lines = self._extract_related_lines(result)
        related_text = self._format_related_lines_text(related_lines)
        self._set_text(self.related_lines_text, related_text)

        self._highlight_source_lines(related_lines)

    @staticmethod
    def _format_answer_payload(result: Dict[str, Any]) -> str:
        if "answer" in result and isinstance(result.get("answer"), str):
            text = result["answer"]
            extras = {k: v for k, v in result.items() if k not in {"answer", "related_lines"}}
            if extras:
                return text + "\n\n--- metadata ---\n" + json.dumps(extras, indent=2, ensure_ascii=False)
            return text
        return json.dumps(result, indent=2, ensure_ascii=False)

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

    def _format_related_lines_text(self, lines: List[int]) -> str:
        if not lines:
            return "(No related lines provided)"

        src_path = self.source_file_var.get().strip() or "json_parser.py"
        try:
            source_lines = Path(src_path).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return f"Could not read source file: {exc}"

        chunks: List[str] = []
        for ln in lines:
            if 1 <= ln <= len(source_lines):
                chunks.append(f"L{ln}: {source_lines[ln - 1]}")
        return "\n".join(chunks) if chunks else "(Related lines are outside file range)"

    @staticmethod
    def _set_text(widget: Any, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    def _highlight_source_lines(self, lines: List[int]) -> None:
        self.source_text.configure(state=tk.NORMAL)
        self.source_text.tag_remove("line_highlight", "1.0", tk.END)

        # determine max line in widget to avoid invalid ranges
        end_index = self.source_text.index("end-1c")
        max_line = int(end_index.split(".")[0]) if end_index else 1

        for ln in lines:
            if 1 <= ln <= max_line:
                start = f"{ln}.0"
                end = f"{ln}.0 lineend"
                self.source_text.tag_add("line_highlight", start, end)

        if lines:
            first = min(ln for ln in lines if ln > 0)
            self.source_text.see(f"{first}.0")

        self.source_text.configure(state=tk.DISABLED)


def run_gui() -> None:
    # On many remote Linux servers there is no X display.
    if os.name != "nt" and not os.environ.get("DISPLAY"):
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
