import unittest
from unittest import mock

from maca.display import OrchestratorDisplay


class TestOrchestratorDisplay(unittest.TestCase):
    def setUp(self):
        self.mock_console = mock.MagicMock()
        self.display = OrchestratorDisplay(self.mock_console)

    def test_show_task_header(self):
        self.display.show_task_header("Build API", "/path/to/repo", "src")
        self.mock_console.print.assert_called_once()

    def test_show_complexity(self):
        self.display.show_complexity("MEDIUM")
        self.mock_console.print.assert_called_once()
        self.assertIn("MEDIUM", self.mock_console.print.call_args[0][0])

    def test_show_model_selection(self):
        self.display.show_model_selection("GEMINI (REMOTE)", model_override="gemini")
        self.assertEqual(self.mock_console.print.call_count, 2)

    def test_show_plan(self):
        self.display.show_plan("1. Step one", ".maca/test/plan.md")
        self.assertEqual(self.mock_console.print.call_count, 2)

    def test_show_spec(self):
        self.display.show_spec("Spec details", ".maca/test/spec.md")
        self.assertEqual(self.mock_console.print.call_count, 2)

    def test_show_generated_files(self):
        self.display.show_generated_files({"a.py": "code"}, "raw response")
        self.assertGreaterEqual(self.mock_console.print.call_count, 2)

    def test_show_pre_review_files(self):
        records = [{"path": "a.py", "action": "CREATE", "size": "100"}]
        self.display.show_pre_review_files(records, {"a.py": "code"}, sandbox_read_only=False)
        self.mock_console.print.assert_called_once()

    def test_show_review_report(self):
        self.display.show_review_report("APPROVED", attempt=1)
        self.mock_console.print.assert_called_once()

    def test_show_task_completed(self):
        self.display.show_task_completed(is_dry_run=False)
        self.mock_console.print.assert_called_once()


if __name__ == "__main__":
    unittest.main()
