import unittest
from unittest import mock

from maca.evaluator import ComplexityEvaluator
from maca.models.gemini import GeminiClient
from maca.models.local_gemma import LocalGemmaClient
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


if __name__ == "__main__":
    unittest.main()
