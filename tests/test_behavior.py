import tempfile
import unittest
from unittest import mock

from maca import maca_config as config
from maca.evaluator import ComplexityEvaluator
from maca.models.claude import ClaudeClient
from maca.models.gemini import GeminiClient
from maca.models.local_gemma import LocalGemmaClient
from maca.orchestrator import Orchestrator


class BehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_heuristic_evaluate_marks_database_task_as_complex(self):
        evaluator = ComplexityEvaluator()

        with mock.patch.object(
            evaluator.gemma_client, "generate", side_effect=Exception("offline")
        ):
            result = evaluator.evaluate("Build a Flask API with SQL database integration")

        self.assertEqual(result, "COMPLEX")

    def test_heuristic_evaluate_marks_short_prompt_as_simple(self):
        evaluator = ComplexityEvaluator()

        with mock.patch.object(
            evaluator.gemma_client, "generate", side_effect=Exception("offline")
        ):
            result = evaluator.evaluate("Write a hello world script")

        self.assertEqual(result, "SIMPLE")

    def test_spring_boot_hello_world_classified_as_complex(self):
        evaluator = ComplexityEvaluator()

        # Heuristic fallback path
        with mock.patch.object(
            evaluator.gemma_client, "generate", side_effect=Exception("offline")
        ):
            result = evaluator.evaluate("Creating a hello world spring boot app")
        self.assertEqual(result, "COMPLEX")

        # Model evaluation with guardrail against naive SIMPLE downgrade
        with mock.patch.object(evaluator.gemma_client, "generate", return_value="SIMPLE"):
            guarded_result = evaluator.evaluate("Creating a hello world spring boot app")
        self.assertEqual(guarded_result, "COMPLEX")

    def test_mock_generators_spring_boot_produce_java_and_pom(self):
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = True
        try:
            prompt = "Creating a hello world spring boot app"

            # Local Gemma Client mock
            gemma = LocalGemmaClient()
            with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("offline")):
                with mock.patch("subprocess.run", side_effect=FileNotFoundError):
                    gemma_plan = gemma.generate(prompt, "You are a planner")
                    gemma_code = gemma.generate(prompt, "You are a coder")
            self.assertIn("pom.xml", gemma_plan)
            self.assertIn("DemoApplication.java", gemma_code)
            self.assertNotIn("output_gemma.py", gemma_code)

            # Gemini Client mock
            gemini = GeminiClient()
            with mock.patch.object(gemini, "api_key", ""):
                gemini_code = gemini.generate(prompt, "You are a coder")
            self.assertIn("pom.xml", gemini_code)
            self.assertIn("DemoApplication.java", gemini_code)
            self.assertNotIn("output_gemini.py", gemini_code)

            # Claude Client mock
            claude = ClaudeClient()
            with mock.patch.object(claude, "api_key", ""):
                claude_code = claude.generate(prompt, "You are a coder")
            self.assertIn("pom.xml", claude_code)
            self.assertIn("DemoApplication.java", claude_code)
            self.assertNotIn("output_claude.py", claude_code)
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock

    def test_mock_generators_spring_boot_with_gradle_produce_gradle_and_java(self):
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = True
        try:
            prompt = "Creating a hello world spring boot app with Gradle"

            # Local Gemma Client mock
            gemma = LocalGemmaClient()
            with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("offline")):
                with mock.patch("subprocess.run", side_effect=FileNotFoundError):
                    gemma_plan = gemma.generate(prompt, "You are a planner")
                    gemma_code = gemma.generate(prompt, "You are a coder")
            self.assertIn("build.gradle.kts", gemma_plan)
            self.assertIn("build.gradle.kts", gemma_code)
            self.assertIn("DemoApplication.java", gemma_code)
            self.assertNotIn("pom.xml", gemma_code)

            # Gemini Client mock
            gemini = GeminiClient()
            with mock.patch.object(gemini, "api_key", ""):
                gemini_code = gemini.generate(prompt, "You are a coder")
            self.assertIn("build.gradle.kts", gemini_code)
            self.assertIn("DemoApplication.java", gemini_code)

            # Claude Client mock
            claude = ClaudeClient()
            with mock.patch.object(claude, "api_key", ""):
                claude_code = claude.generate(prompt, "You are a coder")
            self.assertIn("build.gradle.kts", claude_code)
            self.assertIn("DemoApplication.java", claude_code)
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock

    def test_mock_generators_spring_framework_produces_spring_context(self):
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = True
        try:
            prompt = "Configure a Spring Framework MVC webapp"
            gemini = GeminiClient()
            with mock.patch.object(gemini, "api_key", ""):
                code = gemini.generate(prompt, "You are a coder")
            self.assertIn("spring-context", code)
            self.assertIn("AppConfig.java", code)
            self.assertNotIn("spring-boot", code)
            self.assertNotIn("SpringBootApplication", code)
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock

    def test_mock_generators_plain_java_produces_main_java(self):
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = True
        try:
            prompt = "Write a binary search algorithm in Java"
            gemini = GeminiClient()
            with mock.patch.object(gemini, "api_key", ""):
                code = gemini.generate(prompt, "You are a coder")
            self.assertIn("Main.java", code)
            self.assertNotIn("pom.xml", code)
            self.assertNotIn("spring", code.lower())
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock

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

        with (
            mock.patch("urllib.request.urlopen", side_effect=fake_http_error),
            mock.patch("subprocess.run") as run_mock,
        ):
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
        orch = Orchestrator(self.temp_dir.name)
        with (
            mock.patch.object(orch, "_is_gemini_online", return_value=True),
            mock.patch.object(orch, "_is_claude_online", return_value=True),
            mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"),
            mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"),
            mock.patch.object(config, "get_claude_api_key", return_value="fake_key"),
            mock.patch("maca.orchestrator.PlannerAgent") as mock_planner,
        ):
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
        orch = Orchestrator(self.temp_dir.name)
        with (
            mock.patch.object(orch, "_is_gemini_online", return_value=False),
            mock.patch.object(orch, "_is_claude_online", return_value=True),
            mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"),
            mock.patch.object(config, "get_gemini_api_key", return_value=""),
            mock.patch.object(config, "get_claude_api_key", return_value="fake_key"),
            mock.patch("maca.orchestrator.PlannerAgent") as mock_planner,
        ):
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
        orch = Orchestrator(self.temp_dir.name)
        with (
            mock.patch.object(orch, "_is_gemini_online", return_value=True),
            mock.patch.object(orch, "_is_claude_online", return_value=True),
            mock.patch.object(orch.evaluator, "evaluate", return_value="COMPLEX"),
            mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"),
            mock.patch.object(config, "get_claude_api_key", return_value="fake_key"),
            mock.patch("maca.orchestrator.PlannerAgent") as mock_planner,
        ):
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
        orch = Orchestrator(self.temp_dir.name)
        with (
            mock.patch.object(orch, "_is_gemini_online", return_value=True),
            mock.patch.object(orch, "_is_claude_online", return_value=False),
            mock.patch.object(orch.evaluator, "evaluate", return_value="COMPLEX"),
            mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"),
            mock.patch.object(config, "get_claude_api_key", return_value=""),
            mock.patch("maca.orchestrator.PlannerAgent") as mock_planner,
        ):
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
        orch = Orchestrator(self.temp_dir.name)

        is_done_mock = mock.Mock()
        is_done_mock.side_effect = [
            (False, "Missing step 2 implementation"),
            (True, "All steps completed successfully"),
        ]

        mock_plan = "1. Step one\n2. Step two"

        coder_run_mock = mock.Mock()
        coder_run_mock.side_effect = [
            "Generated content for step 1",
            "Generated content for step 1 and 2",
        ]

        reviewer_run_mock = mock.Mock()
        reviewer_run_mock.return_value = "APPROVED"

        with (
            mock.patch.object(orch, "_is_gemini_online", return_value=True),
            mock.patch.object(orch, "_is_claude_online", return_value=False),
            mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"),
            mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"),
            mock.patch.object(config, "SANDBOX_READ_ONLY", True),
            mock.patch("maca.orchestrator.PlannerAgent") as mock_planner_cls,
            mock.patch("maca.orchestrator.SpecAgent") as mock_spec_cls,
            mock.patch("maca.orchestrator.Prompt.ask", return_value=""),
            mock.patch("maca.orchestrator.SpecCoderAgent") as mock_coder_cls,
            mock.patch("maca.orchestrator.ReviewerAgent") as mock_reviewer_cls,
            mock.patch.object(orch, "_is_coder_done", is_done_mock),
        ):
            planner_inst = mock_planner_cls.return_value
            planner_inst.list_files.return_value = []
            planner_inst.run.return_value = mock_plan

            spec_inst = mock_spec_cls.return_value
            spec_inst.run.return_value = "Mock Spec"
            spec_inst.read_file.return_value = "Mock Spec"

            coder_inst = mock_coder_cls.return_value
            coder_inst.run = coder_run_mock
            coder_inst.parse_files.side_effect = [
                {"file1.py": "content1"},
                {"file1.py": "content1_updated"},
            ]

            reviewer_inst = mock_reviewer_cls.return_value
            reviewer_inst.run = reviewer_run_mock
            reviewer_inst.parse_files.return_value = {}
            reviewer_inst.is_approved.side_effect = lambda x: "APPROVED" in x.upper()

            orch.run_task("Implement task")

            self.assertEqual(coder_run_mock.call_count, 2)

            second_call_args = coder_run_mock.call_args_list[1]
            self.assertIn(
                "Nudge: You have not completed all the steps in the plan",
                second_call_args[1]["task_description"],
            )
            self.assertIn("Missing step 2 implementation", second_call_args[1]["task_description"])

            reviewer_run_mock.assert_called_once()

    def test_reviewer_rejection_nudge_loop(self):
        orch = Orchestrator(self.temp_dir.name)

        mock_plan = "1. Step one"

        coder_run_mock = mock.Mock()
        coder_run_mock.side_effect = ["Initial coder response", "Corrected coder response"]

        reviewer_run_mock = mock.Mock()
        reviewer_run_mock.side_effect = [
            "Issues found: missing docstring. REJECTED.",
            "Looks perfect. APPROVED.",
        ]

        with (
            mock.patch.object(orch, "_is_gemini_online", return_value=True),
            mock.patch.object(orch, "_is_claude_online", return_value=False),
            mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"),
            mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"),
            mock.patch.object(config, "SANDBOX_READ_ONLY", True),
            mock.patch("maca.orchestrator.PlannerAgent") as mock_planner_cls,
            mock.patch("maca.orchestrator.SpecAgent") as mock_spec_cls,
            mock.patch("maca.orchestrator.Prompt.ask", return_value=""),
            mock.patch("maca.orchestrator.SpecCoderAgent") as mock_coder_cls,
            mock.patch("maca.orchestrator.ReviewerAgent") as mock_reviewer_cls,
            mock.patch.object(orch, "_is_coder_done", return_value=(True, "Done")),
        ):
            planner_inst = mock_planner_cls.return_value
            planner_inst.list_files.return_value = []
            planner_inst.run.return_value = mock_plan

            spec_inst = mock_spec_cls.return_value
            spec_inst.run.return_value = "Mock Spec"
            spec_inst.read_file.return_value = "Mock Spec"

            coder_inst = mock_coder_cls.return_value
            coder_inst.run = coder_run_mock
            coder_inst.parse_files.side_effect = [
                {"file1.py": "content1"},
                {"file1.py": "content1_updated"},
            ]

            reviewer_inst = mock_reviewer_cls.return_value
            reviewer_inst.run = reviewer_run_mock
            reviewer_inst.parse_files.return_value = {}
            reviewer_inst.is_approved.side_effect = lambda x: "APPROVED" in x.upper()

            orch.run_task("Implement task")

            self.assertEqual(coder_run_mock.call_count, 2)
            self.assertEqual(reviewer_run_mock.call_count, 2)

            second_call_args = coder_run_mock.call_args_list[1]
            self.assertIn(
                "Nudge: The Reviewer has audited your code and raised issues",
                second_call_args[1]["task_description"],
            )
            self.assertIn("missing docstring. REJECTED.", second_call_args[1]["task_description"])

    def test_interactive_command_line_parsing(self):
        import argparse

        from maca.main import parse_interactive_command

        parser = argparse.ArgumentParser()
        parser.add_argument("task", nargs="?", default=None)
        parser.add_argument("--repo", default=".")
        parser.add_argument("--model", default=None)
        parser.add_argument("--mock", action="store_true")

        task, model, is_cmd = parse_interactive_command(
            'maca --model claude "implement a custom tokenizer"', parser
        )
        self.assertTrue(is_cmd)
        self.assertEqual(task, "implement a custom tokenizer")
        self.assertEqual(model, "claude")

        task, model, is_cmd = parse_interactive_command(
            'python3 src/maca/main.py --model gemini "do something"', parser
        )
        self.assertTrue(is_cmd)
        self.assertEqual(task, "do something")
        self.assertEqual(model, "gemini")

        task, model, is_cmd = parse_interactive_command("implement a custom tokenizer", parser)
        self.assertFalse(is_cmd)


if __name__ == "__main__":
    unittest.main()
