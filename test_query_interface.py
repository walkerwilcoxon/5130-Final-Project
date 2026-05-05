import tempfile
import unittest
from pathlib import Path

from query_interface import QueryInterface


def make_query_interface(tmpdir: str) -> QueryInterface:
    source_file = Path(tmpdir) / "sample_source.py"
    source_file.write_text("def demo(name):\n    return f'Hello, {name}'\n", encoding="utf-8")
    return QueryInterface(default_source=str(source_file))


class QueryInterfacePromptTests(unittest.TestCase):
    def test_prompt_overrides_update_rendered_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qi = make_query_interface(tmpdir)
            qi.set_ai_prompt_overrides(
                router_system_prompt="SYSTEM OVERRIDE",
                router_user_prompt_template=(
                    "Question: <QUERY>\n"
                    "File: <SOURCE_FILE>\n"
                    "Code:\n<SOURCE_CODE>"
                ),
            )

            user_prompt = qi._build_ai_user_prompt("What does demo do?")

            self.assertEqual(qi._build_ai_router_prompt(), "SYSTEM OVERRIDE")
            self.assertIn("Question: What does demo do?", user_prompt)
            self.assertIn(f"File: {qi.default_source}", user_prompt)
            self.assertIn("def demo(name):", user_prompt)

    def test_reset_prompt_overrides_restores_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qi = make_query_interface(tmpdir)
            default_info = qi.get_ai_info()

            qi.set_ai_prompt_overrides(
                router_system_prompt="SYSTEM OVERRIDE",
                router_user_prompt_template="Question: <QUERY>",
            )
            qi.reset_ai_prompt_overrides()

            info = qi.get_ai_info()

            self.assertEqual(info["router_system_prompt"], default_info["default_router_system_prompt"])
            self.assertEqual(
                info["router_user_prompt_template"],
                default_info["default_router_user_prompt_template"],
            )

    def test_estimate_ai_input_tokens_accepts_preview_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qi = make_query_interface(tmpdir)

            estimated = qi.estimate_ai_input_tokens(
                natural_language_query="abc",
                router_system_prompt="sys",
                router_user_prompt_template="user: <QUERY>",
            )

            expected_chars = len("sys") + len("user: abc")
            self.assertEqual(estimated, max(1, int(expected_chars / 4)))


if __name__ == "__main__":
    unittest.main()
