import unittest
from unittest import mock

from maca.evaluator import ComplexityEvaluator
from maca.models.gemini import GeminiClient
from maca.models.claude import ClaudeClient
from maca.models.local_gemma import LocalGemmaClient
from maca.orchestrator import Orchestrator
from maca import maca_config as config


class BehaviorTests(unittest.TestCase):
    def test_heuristic_evaluate_marks_database_task_as_complex(self):
        evaluator = ComplexityEvaluator()

        with mock.patch.object(evaluator.gemma_client, "generate", side_effect=Exception("offline")):
            result = evaluator.evaluate("Build a Flask API with SQL database integration")

        self.assertEqual(result, "COMPLEX")

    def test_heuristic_evaluate_marks_short_prompt_as_simple(self):
        evaluator = ComplexityEvaluator()

        with mock.patch.object(evaluator.gemma_client, "generate", side_effect=Exception("offline")):
            result = evaluator.evaluate("Write a hello world script")

        self.assertEqual(result, "SIMPLE")

    def test_gemini_client_returns_mock_response_without_api_key(self):
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = True
        try:
            client = GeminiClient()
            with mock.patch.object(client, "api_key", ""):
                response = client.generate("Create a utility module", "You are a coder")
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock

        self.assertIn("output_gemini.py", response)

    def test_claude_client_returns_mock_response_without_api_key(self):
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = True
        try:
            client = ClaudeClient()
            with mock.patch.object(client, "api_key", ""):
                response = client.generate("Create a utility module", "You are a coder")
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock

        self.assertIn("output_claude.py", response)

    def test_local_gemma_client_falls_back_to_cli(self):
        client = LocalGemmaClient()
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = False

        fake_http_error = RuntimeError("boom")

        with mock.patch("urllib.request.urlopen", side_effect=fake_http_error), \
             mock.patch("subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "CLI response"

            result = client.generate("hello", "You are a coder")

        config.MOCK_GEMMA_FALLBACK = old_mock

        self.assertEqual(result, "CLI response")
        run_mock.assert_called_once()

    def test_gemini_config_uses_maca_config(self):
        old_model = config.GEMINI_MODEL
        old_timeout = config.GEMINI_TIMEOUT_SECONDS
        try:
            config.GEMINI_MODEL = "gemini-test-model"
            config.GEMINI_TIMEOUT_SECONDS = 12.5
            client = GeminiClient()
            self.assertEqual(client.model, "gemini-test-model")
            self.assertEqual(client.timeout, 12.5)
        finally:
            config.GEMINI_MODEL = old_model
            config.GEMINI_TIMEOUT_SECONDS = old_timeout

    def test_claude_config_uses_maca_config(self):
        old_model = config.CLAUDE_MODEL
        old_timeout = config.CLAUDE_TIMEOUT_SECONDS
        try:
            config.CLAUDE_MODEL = "claude-test-model"
            config.CLAUDE_TIMEOUT_SECONDS = 15.5
            client = ClaudeClient()
            self.assertEqual(client.model, "claude-test-model")
            self.assertEqual(client.timeout, 15.5)
        finally:
            config.CLAUDE_MODEL = old_model
            config.CLAUDE_TIMEOUT_SECONDS = old_timeout

    def test_routing_matrix_medium_both_online(self):
        orch = Orchestrator(".")
        with mock.patch.object(orch, "_is_gemini_online", return_value=True), \
             mock.patch.object(orch, "_is_claude_online", return_value=True), \
             mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"), \
             mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"), \
             mock.patch.object(config, "get_claude_api_key", return_value="fake_key"), \
             mock.patch("maca.orchestrator.PlannerAgent") as mock_planner:

            mock_planner.side_effect = RuntimeError("abort_task")
            try:
                orch.run_task("dummy task")
            except RuntimeError as e:
                if str(e) != "abort_task":
                    raise

            mock_planner.assert_called_once()
            called_client = mock_planner.call_args[0][0]
            self.assertIsInstance(called_client, GeminiClient)

    def test_routing_matrix_medium_only_claude_online(self):
        orch = Orchestrator(".")
        with mock.patch.object(orch, "_is_gemini_online", return_value=False), \
             mock.patch.object(orch, "_is_claude_online", return_value=True), \
             mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"), \
             mock.patch.object(config, "get_gemini_api_key", return_value=""), \
             mock.patch.object(config, "get_claude_api_key", return_value="fake_key"), \
             mock.patch("maca.orchestrator.PlannerAgent") as mock_planner:

            mock_planner.side_effect = RuntimeError("abort_task")
            try:
                orch.run_task("dummy task")
            except RuntimeError as e:
                if str(e) != "abort_task":
                    raise

            mock_planner.assert_called_once()
            called_client = mock_planner.call_args[0][0]
            self.assertIsInstance(called_client, ClaudeClient)

    def test_routing_matrix_complex_both_online(self):
        orch = Orchestrator(".")
        with mock.patch.object(orch, "_is_gemini_online", return_value=True), \
             mock.patch.object(orch, "_is_claude_online", return_value=True), \
             mock.patch.object(orch.evaluator, "evaluate", return_value="COMPLEX"), \
             mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"), \
             mock.patch.object(config, "get_claude_api_key", return_value="fake_key"), \
             mock.patch("maca.orchestrator.PlannerAgent") as mock_planner:

            mock_planner.side_effect = RuntimeError("abort_task")
            try:
                orch.run_task("dummy task")
            except RuntimeError as e:
                if str(e) != "abort_task":
                    raise

            mock_planner.assert_called_once()
            called_client = mock_planner.call_args[0][0]
            self.assertIsInstance(called_client, ClaudeClient)

    def test_routing_matrix_complex_only_gemini_online(self):
        orch = Orchestrator(".")
        with mock.patch.object(orch, "_is_gemini_online", return_value=True), \
             mock.patch.object(orch, "_is_claude_online", return_value=False), \
             mock.patch.object(orch.evaluator, "evaluate", return_value="COMPLEX"), \
             mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"), \
             mock.patch.object(config, "get_claude_api_key", return_value=""), \
             mock.patch("maca.orchestrator.PlannerAgent") as mock_planner:

            mock_planner.side_effect = RuntimeError("abort_task")
            try:
                orch.run_task("dummy task")
            except RuntimeError as e:
                if str(e) != "abort_task":
                    raise

            mock_planner.assert_called_once()
            called_client = mock_planner.call_args[0][0]
            self.assertIsInstance(called_client, GeminiClient)

    def test_coder_completion_verification_loop(self):
        orch = Orchestrator(".")

        is_done_mock = mock.Mock()
        is_done_mock.side_effect = [
            (False, "Missing step 2 implementation"),
            (True, "All steps completed successfully")
        ]

        mock_plan = "1. Step one\n2. Step two"

        coder_run_mock = mock.Mock()
        coder_run_mock.side_effect = [
            "Generated content for step 1",
            "Generated content for step 1 and 2"
        ]

        reviewer_run_mock = mock.Mock()
        reviewer_run_mock.return_value = "APPROVED"

        with mock.patch.object(orch, "_is_gemini_online", return_value=True), \
             mock.patch.object(orch, "_is_claude_online", return_value=False), \
             mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"), \
             mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"), \
             mock.patch.object(config, "SANDBOX_READ_ONLY", True), \
             mock.patch("maca.orchestrator.PlannerAgent") as mock_planner_cls, \
             mock.patch("maca.orchestrator.CoderAgent") as mock_coder_cls, \
             mock.patch("maca.orchestrator.ReviewerAgent") as mock_reviewer_cls, \
             mock.patch.object(orch, "_is_coder_done", is_done_mock):

            planner_inst = mock_planner_cls.return_value
            planner_inst.list_files.return_value = []
            planner_inst.run.return_value = mock_plan

            coder_inst = mock_coder_cls.return_value
            coder_inst.run = coder_run_mock
            coder_inst.parse_files.side_effect = [
                {"file1.py": "content1"},
                {"file1.py": "content1_updated"}
            ]

            reviewer_inst = mock_reviewer_cls.return_value
            reviewer_inst.run = reviewer_run_mock
            reviewer_inst.parse_files.return_value = {}

            orch.run_task("Implement task")

            self.assertEqual(coder_run_mock.call_count, 2)

            second_call_args = coder_run_mock.call_args_list[1]
            self.assertIn("Nudge: You have not completed all the steps in the plan", second_call_args[1]["task_description"])
            self.assertIn("Missing step 2 implementation", second_call_args[1]["task_description"])

            reviewer_run_mock.assert_called_once()

    def test_reviewer_rejection_nudge_loop(self):
        orch = Orchestrator(".")

        mock_plan = "1. Step one"

        coder_run_mock = mock.Mock()
        coder_run_mock.side_effect = [
            "Initial coder response",
            "Corrected coder response"
        ]

        reviewer_run_mock = mock.Mock()
        reviewer_run_mock.side_effect = [
            "Issues found: missing docstring. REJECTED.",
            "Looks perfect. APPROVED."
        ]

        with mock.patch.object(orch, "_is_gemini_online", return_value=True), \
             mock.patch.object(orch, "_is_claude_online", return_value=False), \
             mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"), \
             mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"), \
             mock.patch.object(config, "SANDBOX_READ_ONLY", True), \
             mock.patch("maca.orchestrator.PlannerAgent") as mock_planner_cls, \
             mock.patch("maca.orchestrator.CoderAgent") as mock_coder_cls, \
             mock.patch("maca.orchestrator.ReviewerAgent") as mock_reviewer_cls, \
             mock.patch.object(orch, "_is_coder_done", return_value=(True, "Done")):

            planner_inst = mock_planner_cls.return_value
            planner_inst.list_files.return_value = []
            planner_inst.run.return_value = mock_plan

            coder_inst = mock_coder_cls.return_value
            coder_inst.run = coder_run_mock
            coder_inst.parse_files.side_effect = [
                {"file1.py": "content1"},
                {"file1.py": "content1_updated"}
            ]

            reviewer_inst = mock_reviewer_cls.return_value
            reviewer_inst.run = reviewer_run_mock
            reviewer_inst.parse_files.return_value = {}

            orch.run_task("Implement task")

            self.assertEqual(coder_run_mock.call_count, 2)
            self.assertEqual(reviewer_run_mock.call_count, 2)

            second_call_args = coder_run_mock.call_args_list[1]
            self.assertIn("Nudge: The Reviewer has audited your code and raised issues", second_call_args[1]["task_description"])
            self.assertIn("missing docstring. REJECTED.", second_call_args[1]["task_description"])

    def test_interactive_command_line_parsing(self):
        from maca.main import parse_interactive_command
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("task", nargs="?", default=None)
        parser.add_argument("--repo", default=".")
        parser.add_argument("--model", default=None)
        parser.add_argument("--mock", action="store_true")

        task, model, is_cmd = parse_interactive_command('maca --model claude "implement a custom tokenizer"', parser)
        self.assertTrue(is_cmd)
        self.assertEqual(task, "implement a custom tokenizer")
        self.assertEqual(model, "claude")

        task, model, is_cmd = parse_interactive_command('python3 src/maca/main.py --model gemini "do something"', parser)
        self.assertTrue(is_cmd)
        self.assertEqual(task, "do something")
        self.assertEqual(model, "gemini")

        task, model, is_cmd = parse_interactive_command('implement a custom tokenizer', parser)
        self.assertFalse(is_cmd)


if __name__ == "__main__":
    unittest.main()
