import json
import math
import os
import unittest
from dataclasses import FrozenInstanceError
from typing import Any
from unittest import mock

from maca import maca_config as config
from maca.agents.base import BaseAgent
from maca.agents.coder import SimpleCoderAgent
from maca.models.claude import ClaudeClient
from maca.models.gemini import GeminiClient
from maca.models.local_gemma import LocalGemmaClient
from maca.token_budget import (
    TokenBudgetResult,
    compute_input_budget,
    enforce_token_budget,
    estimate_tokens,
)


def _make_json_response(payload: Any) -> mock.MagicMock:
    raw = json.dumps(payload).encode("utf-8")
    resp = mock.MagicMock()
    resp.read.return_value = raw
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


class _DummyAgent(BaseAgent):
    def __init__(self, model_client: Any, system_text: str = "System rules"):
        super().__init__("DummyAgent", model_client)
        self._system_text = system_text

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return self._system_text

    def _build_prompt(self, prompt_text: str, *args: Any, **kwargs: Any) -> str:
        return prompt_text


class TestTokenBudget(unittest.TestCase):
    def setUp(self):
        LocalGemmaClient.clear_context_window_cache()

    def tearDown(self):
        LocalGemmaClient.clear_context_window_cache()

    def test_estimate_tokens_empty_and_non_empty(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("a"), 1)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcde"), 2)
        self.assertEqual(estimate_tokens("x" * 400), 100)
        self.assertEqual(estimate_tokens("deterministic"), estimate_tokens("deterministic"))

    def test_compute_input_budget_default_and_clamping(self):
        self.assertEqual(compute_input_budget(1000), 700)
        self.assertEqual(compute_input_budget(1000, 0.25), 750)
        self.assertEqual(compute_input_budget(16384, 0.30), 11469)

        # Clamped to [0.05, 0.80]
        self.assertEqual(compute_input_budget(1000, 0.0), 950)
        self.assertEqual(compute_input_budget(1000, -0.5), 950)
        self.assertEqual(compute_input_budget(1000, 0.95), 200)
        self.assertEqual(compute_input_budget(1000, 2.0), 200)
        self.assertEqual(compute_input_budget(1000, float("nan")), 700)

        # Non-positive context window disables budget
        self.assertEqual(compute_input_budget(0), 0)
        self.assertEqual(compute_input_budget(-100), 0)
        self.assertEqual(compute_input_budget(1, 0.80), 1)

    def test_result_dataclass_is_frozen(self):
        result = enforce_token_budget("hello", "sys", max_context_tokens=100)
        self.assertIsInstance(result, TokenBudgetResult)
        with self.assertRaises(FrozenInstanceError):
            setattr(result, "trimmed", True)

    def test_enforce_token_budget_noop_when_within_budget(self):
        prompt = "Write a helper function to sort integers."
        system_instruction = "You are a concise coding assistant."
        result = enforce_token_budget(
            prompt=prompt,
            system_instruction=system_instruction,
            max_context_tokens=1024,
            output_reserve_ratio=0.30,
        )
        self.assertFalse(result.trimmed)
        self.assertEqual(result.warning, "")
        self.assertEqual(result.prompt, prompt)
        self.assertEqual(result.system_instruction, system_instruction)
        self.assertEqual(result.max_context_tokens, 1024)
        self.assertEqual(result.input_budget_tokens, compute_input_budget(1024, 0.30))
        expected_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
        self.assertEqual(result.estimated_input_tokens, expected_tokens)

    def test_enforce_token_budget_disabled_when_max_context_non_positive(self):
        large_prompt = "A" * 10000
        result = enforce_token_budget(large_prompt, "sys", max_context_tokens=0)
        self.assertFalse(result.trimmed)
        self.assertEqual(result.warning, "")
        self.assertEqual(result.prompt, large_prompt)
        self.assertEqual(result.input_budget_tokens, 0)

    def test_enforce_token_budget_head_tail_trimming_marker_and_warning(self):
        head_marker = "OPENING_TASK_INSTRUCTIONS: Build a parser.\n"
        tail_marker = "\nCLOSING_NUDGE: Output [FILE: parser.py] now."
        middle_filler = "M" * 4000
        prompt = f"{head_marker}{middle_filler}{tail_marker}"
        system_instruction = "You are a strict coding agent."

        result = enforce_token_budget(
            prompt=prompt,
            system_instruction=system_instruction,
            max_context_tokens=400,
            output_reserve_ratio=0.30,
        )

        self.assertTrue(result.trimmed)
        self.assertEqual(result.system_instruction, system_instruction)
        self.assertTrue(result.prompt.startswith(head_marker))
        self.assertTrue(result.prompt.endswith(tail_marker))
        self.assertIn("[... truncated ", result.prompt)
        self.assertIn(" chars to fit context budget ...]", result.prompt)

        final_tokens = estimate_tokens(result.prompt) + estimate_tokens(result.system_instruction)
        self.assertLessEqual(final_tokens, result.input_budget_tokens)

        self.assertIn(str(result.estimated_input_tokens), result.warning)
        self.assertIn(str(result.input_budget_tokens), result.warning)
        self.assertIn("CONTEXT_TOKEN_BUDGET", result.warning)
        self.assertIn("OLLAMA_NUM_CTX", result.warning)

    def test_enforce_token_budget_extreme_system_instruction_exceeds_budget(self):
        sys_head = "SYS_HEAD_RULES: Always follow clean code.\n"
        sys_tail = "\nSYS_TAIL_FORMAT: Use [FILE: path]."
        system_instruction = f"{sys_head}{'S' * 4000}{sys_tail}"
        prompt_head = "USER_HEAD: Implement feature.\n"
        prompt_tail = "\nUSER_TAIL: Keep it modular."
        prompt = f"{prompt_head}{'P' * 2000}{prompt_tail}"

        result = enforce_token_budget(
            prompt=prompt,
            system_instruction=system_instruction,
            max_context_tokens=400,
            output_reserve_ratio=0.30,
        )

        self.assertTrue(result.trimmed)
        self.assertLess(len(result.system_instruction), len(system_instruction))
        self.assertTrue(result.system_instruction.startswith(sys_head))
        self.assertTrue(result.system_instruction.endswith(sys_tail))
        self.assertTrue(result.prompt.startswith(prompt_head))
        self.assertTrue(result.prompt.endswith(prompt_tail))

        final_tokens = estimate_tokens(result.prompt) + estimate_tokens(result.system_instruction)
        self.assertLessEqual(final_tokens, result.input_budget_tokens)
        self.assertIn("system_instruction alone", result.warning)
        self.assertIn("CONTEXT_TOKEN_BUDGET", result.warning)
        self.assertIn("OLLAMA_NUM_CTX", result.warning)

    def test_enforce_token_budget_extreme_system_with_short_prompt_preserves_prompt(self):
        system_instruction = "S" * 3000
        short_prompt = "Fix bug."

        result = enforce_token_budget(
            prompt=short_prompt,
            system_instruction=system_instruction,
            max_context_tokens=300,
            output_reserve_ratio=0.30,
        )

        self.assertTrue(result.trimmed)
        self.assertEqual(result.prompt, short_prompt)
        final_tokens = estimate_tokens(result.prompt) + estimate_tokens(result.system_instruction)
        self.assertLessEqual(final_tokens, result.input_budget_tokens)

    def test_enforce_token_budget_tiny_context_budget_never_exceeds_limit(self):
        result = enforce_token_budget(
            prompt="P" * 500,
            system_instruction="S" * 500,
            max_context_tokens=16,
            output_reserve_ratio=0.30,
        )
        self.assertTrue(result.trimmed)
        final_tokens = estimate_tokens(result.prompt) + estimate_tokens(result.system_instruction)
        self.assertLessEqual(final_tokens, result.input_budget_tokens)

    def test_config_env_parsers_handle_invalid_values(self):
        self.assertEqual(config._parse_int_env("8192", 16384), 8192)
        self.assertEqual(config._parse_int_env("not-an-int", 16384), 16384)
        self.assertEqual(config._parse_int_env("", 16384), 16384)
        self.assertEqual(config._parse_int_env(None, 16384), 16384)

        self.assertEqual(config._parse_optional_nonneg_int_env("0"), 0)
        self.assertEqual(config._parse_optional_nonneg_int_env("4096"), 4096)
        self.assertIsNone(config._parse_optional_nonneg_int_env("-1"))
        self.assertIsNone(config._parse_optional_nonneg_int_env("bad"))
        self.assertIsNone(config._parse_optional_nonneg_int_env(""))
        self.assertIsNone(config._parse_optional_nonneg_int_env(None))

        self.assertAlmostEqual(config._parse_float_env("0.25", 0.30), 0.25)
        self.assertAlmostEqual(config._parse_float_env("bad", 0.30), 0.30)
        self.assertAlmostEqual(config._parse_float_env("nan", 0.30), 0.30)
        self.assertAlmostEqual(config._parse_float_env("inf", 0.30), 0.30)
        self.assertFalse(math.isnan(config._parse_float_env("nan", 0.30)))

    def test_cloud_clients_return_smart_context_window_defaults_and_overrides(self):
        gemini = GeminiClient()
        claude = ClaudeClient()

        self.assertEqual(gemini.get_context_window(), config.GEMINI_CONTEXT_WINDOW)
        self.assertEqual(claude.get_context_window(), config.CLAUDE_CONTEXT_WINDOW)

        with mock.patch.object(config, "GEMINI_CONTEXT_WINDOW", 524288):
            self.assertEqual(gemini.get_context_window(), 524288)

        with mock.patch.object(config, "CLAUDE_CONTEXT_WINDOW", 128000):
            self.assertEqual(claude.get_context_window(), 128000)

    def test_local_gemma_discovers_context_length_and_caches(self):
        client = LocalGemmaClient()
        payload = {"model_info": {"gemma2.context_length": 8192}}

        with mock.patch.object(config, "MOCK_GEMMA_FALLBACK", False):
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OLLAMA_NUM_CTX", None)
                with mock.patch(
                    "urllib.request.urlopen", return_value=_make_json_response(payload)
                ) as mock_urlopen:
                    first = client.get_context_window()
                    second = client.get_context_window()

        self.assertEqual(first, 8192)
        self.assertEqual(second, 8192)
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertTrue(req.full_url.endswith("/api/show"))
        self.assertEqual(json.loads(req.data.decode("utf-8")), {"name": client.model})
        self.assertEqual(mock_urlopen.call_args[1]["timeout"], 3)

    def test_local_gemma_takes_min_of_model_info_and_parameters_num_ctx(self):
        client = LocalGemmaClient()
        payload = {
            "model_info": {"gemma2.context_length": 8192},
            "parameters": "temperature 0.7\nnum_ctx 4096\n",
        }

        resp = _make_json_response(payload)
        with mock.patch.object(config, "MOCK_GEMMA_FALLBACK", False):
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OLLAMA_NUM_CTX", None)
                with mock.patch("urllib.request.urlopen", return_value=resp):
                    self.assertEqual(client.get_context_window(), 4096)

    def test_local_gemma_caps_discovered_window_with_ollama_num_ctx_env(self):
        client = LocalGemmaClient()
        payload = {"model_info": {"gemma2.context_length": 8192}}
        resp = _make_json_response(payload)

        with mock.patch.object(config, "MOCK_GEMMA_FALLBACK", False):
            with mock.patch.dict(os.environ, {"OLLAMA_NUM_CTX": "2048"}, clear=False):
                with mock.patch("urllib.request.urlopen", return_value=resp):
                    self.assertEqual(client.get_context_window(), 2048)

    def test_local_gemma_mock_mode_skips_http(self):
        client = LocalGemmaClient()

        with mock.patch.object(config, "MOCK_GEMMA_FALLBACK", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET", 12345):
                with mock.patch("urllib.request.urlopen") as mock_urlopen:
                    with mock.patch.dict(os.environ, {}, clear=False):
                        os.environ.pop("OLLAMA_NUM_CTX", None)
                        self.assertEqual(client.get_context_window(), 12345)
                    with mock.patch.dict(os.environ, {"OLLAMA_NUM_CTX": "4096"}, clear=False):
                        self.assertEqual(client.get_context_window(), 4096)

        mock_urlopen.assert_not_called()

    def test_local_gemma_offline_fallback_uses_ollama_num_ctx_or_config(self):
        client = LocalGemmaClient()

        with mock.patch.object(config, "MOCK_GEMMA_FALLBACK", False):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET", 16384):
                with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("offline")):
                    with mock.patch.dict(os.environ, {}, clear=False):
                        os.environ.pop("OLLAMA_NUM_CTX", None)
                        self.assertEqual(client.get_context_window(), 16384)

                    LocalGemmaClient.clear_context_window_cache()
                    with mock.patch.dict(os.environ, {"OLLAMA_NUM_CTX": "6144"}, clear=False):
                        self.assertEqual(client.get_context_window(), 6144)

    def test_base_agent_preflight_noop_for_short_prompt(self):
        mock_client = mock.MagicMock()
        mock_client.generate.return_value = "ok"
        agent = _DummyAgent(mock_client, system_text="Short system prompt.")

        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", None):
                with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET", 4096):
                    output = agent.run("Short user prompt.")

        self.assertEqual(output, "ok")
        mock_client.generate.assert_called_once_with("Short user prompt.", "Short system prompt.")
        self.assertIsNotNone(agent.last_budget_result)
        assert agent.last_budget_result is not None
        self.assertFalse(agent.last_budget_result.trimmed)

    def test_base_agent_preflight_trims_and_logs_warning_when_over_budget(self):
        mock_client = mock.MagicMock()
        mock_client.generate.return_value = "trimmed_ok"
        agent = _DummyAgent(mock_client, system_text="Keep rules intact.")
        huge_prompt = f"HEAD_TASK: do work\n{'X' * 3000}\nTAIL_DIRECTIVE: finish."

        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", None):
                with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET", 300):
                    with mock.patch.object(config, "CONTEXT_OUTPUT_RESERVE_RATIO", 0.30):
                        with self.assertLogs("maca.agents.base", level="WARNING") as log_ctx:
                            output = agent.run(huge_prompt)

        self.assertEqual(output, "trimmed_ok")
        mock_client.generate.assert_called_once()
        sent_prompt, sent_system = mock_client.generate.call_args[0]
        self.assertEqual(sent_system, "Keep rules intact.")
        self.assertIn("HEAD_TASK: do work", sent_prompt)
        self.assertIn("TAIL_DIRECTIVE: finish.", sent_prompt)
        self.assertIn("[... truncated ", sent_prompt)
        self.assertIsNotNone(agent.last_budget_result)
        assert agent.last_budget_result is not None
        self.assertTrue(agent.last_budget_result.trimmed)
        self.assertTrue(any("CONTEXT_TOKEN_BUDGET" in msg for msg in log_ctx.output))

    def test_base_agent_model_aware_resizing_local_vs_cloud(self):
        medium_prompt = f"HEAD: Task details\n{'A' * 3000}\nTAIL: Final step."

        # Small local model window (300 tokens) trims the prompt
        local_client = LocalGemmaClient()
        local_agent = _DummyAgent(local_client, system_text="Local rules.")
        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", None):
                with mock.patch.object(local_client, "get_context_window", return_value=300):
                    with mock.patch.object(
                        local_client, "generate", return_value="local_ok"
                    ) as local_gen:
                        with self.assertLogs("maca.agents.base", level="WARNING"):
                            local_out = local_agent.run(medium_prompt)

        self.assertEqual(local_out, "local_ok")
        sent_local_prompt, _ = local_gen.call_args[0]
        self.assertIn("[... truncated ", sent_local_prompt)
        self.assertIsNotNone(local_agent.last_budget_result)
        assert local_agent.last_budget_result is not None
        self.assertTrue(local_agent.last_budget_result.trimmed)
        self.assertEqual(local_agent.last_budget_result.max_context_tokens, 300)

        # Cloud model window (Gemini default 50K) leaves the exact same prompt untouched
        gemini_client = GeminiClient()
        cloud_agent = _DummyAgent(gemini_client, system_text="Cloud rules.")
        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", None):
                with mock.patch.object(config, "GEMINI_CONTEXT_WINDOW", 50000):
                    with mock.patch.object(
                        gemini_client, "generate", return_value="cloud_ok"
                    ) as cloud_gen:
                        cloud_out = cloud_agent.run(medium_prompt)

        self.assertEqual(cloud_out, "cloud_ok")
        cloud_gen.assert_called_once_with(medium_prompt, "Cloud rules.")
        self.assertIsNotNone(cloud_agent.last_budget_result)
        assert cloud_agent.last_budget_result is not None
        self.assertFalse(cloud_agent.last_budget_result.trimmed)
        self.assertEqual(cloud_agent.last_budget_result.max_context_tokens, 50000)

    def test_base_agent_explicit_override_forces_cap_or_disables(self):
        medium_prompt = f"HEAD: Task\n{'B' * 3000}\nTAIL: Done."
        gemini_client = GeminiClient()
        agent = _DummyAgent(gemini_client, system_text="Rules.")

        # Explicit positive override caps even cloud clients
        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", 250):
                with mock.patch.object(
                    gemini_client, "generate", return_value="capped_ok"
                ) as mock_gen:
                    with self.assertLogs("maca.agents.base", level="WARNING"):
                        agent.run(medium_prompt)

        sent_prompt, _ = mock_gen.call_args[0]
        self.assertIn("[... truncated ", sent_prompt)
        self.assertIsNotNone(agent.last_budget_result)
        assert agent.last_budget_result is not None
        self.assertEqual(agent.last_budget_result.max_context_tokens, 250)

        # Explicit 0 override disables budgeting completely
        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", 0):
                with mock.patch.object(
                    gemini_client, "generate", return_value="disabled_ok"
                ) as mock_gen_zero:
                    agent.run(medium_prompt)

        mock_gen_zero.assert_called_once_with(medium_prompt, "Rules.")
        self.assertIsNone(agent.last_budget_result)

    def test_base_agent_preflight_skipped_when_disabled(self):
        mock_client = mock.MagicMock()
        mock_client.generate.return_value = "raw_ok"
        agent = _DummyAgent(mock_client, system_text="Sys")
        huge_prompt = "Z" * 5000

        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", False):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", None):
                with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET", 100):
                    output = agent.run(huge_prompt)

        self.assertEqual(output, "raw_ok")
        mock_client.generate.assert_called_once_with(huge_prompt, "Sys")
        self.assertIsNone(agent.last_budget_result)

    def test_coder_agent_routes_through_preflight_budgeter(self):
        mock_client = mock.MagicMock()
        mock_client.generate.return_value = "[FILE: a.py]\n```python\npass\n```"
        coder = SimpleCoderAgent("SimpleCoder", mock_client)
        huge_files = {"big.py": "x = 1\n" * 2000}

        with mock.patch.object(config, "CONTEXT_BUDGET_ENABLED", True):
            with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET_OVERRIDE", None):
                with mock.patch.object(config, "CONTEXT_TOKEN_BUDGET", 800):
                    with self.assertLogs("maca.agents.base", level="WARNING"):
                        coder.run(
                            task_description="Add feature",
                            plan="1. Update big.py",
                            repo_files_content=huge_files,
                        )

        mock_client.generate.assert_called_once()
        sent_prompt, _ = mock_client.generate.call_args[0]
        self.assertIn("[... truncated ", sent_prompt)
        self.assertIsNotNone(coder.last_budget_result)
        assert coder.last_budget_result is not None
        self.assertTrue(coder.last_budget_result.trimmed)


if __name__ == "__main__":
    unittest.main()
