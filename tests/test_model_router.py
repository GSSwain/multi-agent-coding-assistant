import unittest
from unittest import mock

from maca import maca_config as config
from maca.models.claude import ClaudeClient
from maca.models.gemini import GeminiClient
from maca.models.local_gemma import LocalGemmaClient
from maca.models.router import ModelRouter


class TestModelRouter(unittest.TestCase):
    def test_override_gemini(self):
        with mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"):
            name, client = ModelRouter.select_model("SIMPLE", model_override="gemini")
            self.assertEqual(name, "GEMINI")
            self.assertIsInstance(client, GeminiClient)

    def test_override_claude(self):
        with mock.patch.object(config, "get_claude_api_key", return_value="fake_key"):
            name, client = ModelRouter.select_model("SIMPLE", model_override="claude")
            self.assertEqual(name, "CLAUDE")
            self.assertIsInstance(client, ClaudeClient)

    def test_override_gemma(self):
        name, client = ModelRouter.select_model("COMPLEX", model_override="gemma")
        self.assertEqual(name, "GEMMA")
        self.assertIsInstance(client, LocalGemmaClient)

    def test_simple_defaults_to_gemma(self):
        name, client = ModelRouter.select_model("SIMPLE")
        self.assertEqual(name, "GEMMA (LOCAL)")
        self.assertIsInstance(client, LocalGemmaClient)

    def test_medium_picks_gemini_when_online(self):
        with mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"):
            name, client = ModelRouter.select_model(
                "MEDIUM",
                is_gemini_online_fn=lambda: True,
                is_claude_online_fn=lambda: False,
            )
            self.assertEqual(name, "GEMINI (REMOTE)")
            self.assertIsInstance(client, GeminiClient)

    def test_medium_picks_claude_when_gemini_offline(self):
        with mock.patch.object(config, "get_claude_api_key", return_value="fake_key"):
            name, client = ModelRouter.select_model(
                "MEDIUM",
                is_gemini_online_fn=lambda: False,
                is_claude_online_fn=lambda: True,
            )
            self.assertEqual(name, "CLAUDE (REMOTE)")
            self.assertIsInstance(client, ClaudeClient)

    def test_complex_picks_claude_when_online(self):
        with mock.patch.object(config, "get_claude_api_key", return_value="fake_key"):
            name, client = ModelRouter.select_model(
                "COMPLEX",
                is_gemini_online_fn=lambda: True,
                is_claude_online_fn=lambda: True,
            )
            self.assertEqual(name, "CLAUDE (REMOTE)")
            self.assertIsInstance(client, ClaudeClient)

    def test_complex_falls_back_to_gemini(self):
        with mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"):
            name, client = ModelRouter.select_model(
                "COMPLEX",
                is_gemini_online_fn=lambda: True,
                is_claude_online_fn=lambda: False,
            )
            self.assertEqual(name, "GEMINI (REMOTE)")
            self.assertIsInstance(client, GeminiClient)

    def test_complex_falls_back_to_gemma_when_both_offline(self):
        name, client = ModelRouter.select_model(
            "COMPLEX",
            is_gemini_online_fn=lambda: False,
            is_claude_online_fn=lambda: False,
        )
        self.assertEqual(name, "GEMMA (LOCAL)")
        self.assertIsInstance(client, LocalGemmaClient)


if __name__ == "__main__":
    unittest.main()
