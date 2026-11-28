import os
import tempfile
import unittest
from unittest import mock

from maca.context import TaskContext
from maca.history_compactor import (
    DEFAULT_RECENT_TURNS,
    HistoryCompactor,
    compact_conversation_history,
    get_recent_turns_limit,
)
from maca.orchestrator import Orchestrator
from maca.stages.common import build_agent_payload


class TestHistoryCompactor(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("MACA_HISTORY_RECENT_TURNS", None)

    def test_empty_history_passthrough(self):
        compacted, summary = compact_conversation_history([])
        self.assertEqual(compacted, [])
        self.assertEqual(summary, "")

    def test_short_string_history_passthrough(self):
        history = [
            "User Request: Add greet helper in src/greet.py",
            "Files Modified/Created: src/greet.py",
            "Reviewer Decision: APPROVED",
        ]
        compacted, summary = compact_conversation_history(history)
        self.assertEqual(summary, "")
        self.assertEqual(compacted, history)
        self.assertIsNot(compacted, history)

    def test_short_dict_history_passthrough(self):
        history = [
            {"role": "user", "content": "Create src/app.py"},
            {"role": "assistant", "content": "Created src/app.py"},
        ]
        compacted, summary = compact_conversation_history(history)
        self.assertEqual(summary, "")
        self.assertEqual(compacted, history)
        self.assertIsNot(compacted, history)

    def test_long_string_history_compaction(self):
        history = [
            "User Request: Add OAuth login in src/auth.py. Must preserve session cookies.",
            "Planner Implementation Steps:\n1. Edit src/auth.py\n2. Add tests/test_auth.py",
            "Files Modified/Created: src/auth.py, tests/test_auth.py",
            "Reviewer Decision: APPROVED",
            "User Request: Add rate limiter in src/ratelimit.py",
            "Files Modified/Created: src/ratelimit.py",
            "Reviewer Decision: APPROVED",
        ]
        compacted, summary = compact_conversation_history(history, max_recent=3)

        self.assertEqual(len(compacted), 4)
        self.assertIsInstance(compacted[0], str)
        self.assertEqual(compacted[0], summary)
        self.assertEqual(compacted[1:], history[-3:])
        self.assertIn("Add OAuth login", summary)
        self.assertIn("Must preserve session cookies", summary)
        self.assertIn("APPROVED", summary)
        self.assertIn("src/auth.py", summary)
        self.assertIn("tests/test_auth.py", summary)

    def test_long_dict_history_compaction(self):
        history = [
            {
                "role": "user",
                "content": "Build CLI parser in src/cli.py. Must not add external packages.",
            },
            {
                "role": "assistant",
                "content": "Decision: Use argparse in src/cli.py and tests in tests/test_cli.py.",
            },
            {"role": "system", "content": "Constraint: Strictly support Python 3.9."},
            {"role": "user", "content": "Add --verbose option"},
            {"role": "assistant", "content": "Updated src/cli.py with --verbose"},
            {"role": "user", "content": "Update docs/cli.md"},
        ]
        compacted, summary = compact_conversation_history(history, max_recent=3)

        self.assertEqual(len(compacted), 4)
        self.assertIsInstance(compacted[0], dict)
        self.assertEqual(compacted[0]["role"], "system")
        self.assertEqual(compacted[0]["content"], summary)
        self.assertEqual(compacted[1:], history[-3:])
        self.assertIn("Build CLI parser", summary)
        self.assertIn("argparse", summary)
        self.assertIn("Python 3.9", summary)
        self.assertIn("src/cli.py", summary)
        self.assertIn("tests/test_cli.py", summary)

    def test_rolling_compaction_recompacts_prior_summary(self):
        first_batch = [
            "User Request: Add OAuth in src/auth.py",
            "Files Modified/Created: src/auth.py",
            "Reviewer Decision: APPROVED",
            "User Request: Add tests in tests/test_auth.py",
            "Reviewer Decision: APPROVED",
        ]
        compacted_once, summary_once = compact_conversation_history(first_batch, max_recent=2)
        self.assertIn("src/auth.py", summary_once)

        extended = compacted_once + [
            "User Request: Add docs in docs/oauth.md",
            "Reviewer Decision: APPROVED",
        ]
        compacted_twice, summary_twice = compact_conversation_history(extended, max_recent=2)

        self.assertEqual(len(compacted_twice), 3)
        self.assertEqual(summary_twice.count("Compacted history summary"), 1)
        self.assertIn("src/auth.py", summary_twice)
        self.assertIn("tests/test_auth.py", summary_twice)

    def test_summary_respects_max_summary_chars(self):
        history = [
            f"User Request: Implement verbose requirement number {i} with detailed context "
            f"for module src/mod_{i}.py and strict validation rules."
            for i in range(15)
        ]
        for cap in (400, 200, 80, 30):
            compacted, summary = compact_conversation_history(
                history, max_recent=3, max_summary_chars=cap
            )
            self.assertEqual(len(compacted), 4)
            self.assertGreater(len(summary), 0)
            self.assertLessEqual(len(summary), cap)

    def test_file_path_retention_under_truncation_and_ignores_urls(self):
        long_filler = " ".join(["background"] * 80)
        history = [
            f"User Request: Refactor auth flow {long_filler} touching src/auth/oauth.py "
            "and tests/test_oauth.py. See https://example.com/docs/guide.html for details.",
            "Decision: Keep backwards compatibility with config/settings.json.",
            "Turn 3 recent",
            "Turn 4 recent",
            "Turn 5 recent",
        ]
        _, summary = compact_conversation_history(history, max_recent=3, max_summary_chars=240)

        self.assertLessEqual(len(summary), 240)
        self.assertIn("src/auth/oauth.py", summary)
        self.assertIn("tests/test_oauth.py", summary)
        self.assertIn("config/settings.json", summary)
        self.assertNotIn("guide.html", summary)

    def test_env_var_override_recent_turns(self):
        history = [f"User Request: Task {i}" for i in range(5)]

        with mock.patch.dict(os.environ, {"MACA_HISTORY_RECENT_TURNS": "2"}):
            self.assertEqual(get_recent_turns_limit(), 2)
            compacted, summary = compact_conversation_history(history)
            self.assertEqual(len(compacted), 3)
            self.assertEqual(compacted[1:], history[-2:])
            self.assertNotEqual(summary, "")

        with mock.patch.dict(os.environ, {"MACA_HISTORY_RECENT_TURNS": "invalid"}):
            self.assertEqual(get_recent_turns_limit(), DEFAULT_RECENT_TURNS)

        with mock.patch.dict(os.environ, {"MACA_HISTORY_RECENT_TURNS": "-3"}):
            self.assertEqual(get_recent_turns_limit(), DEFAULT_RECENT_TURNS)

    def test_max_recent_zero_compacts_all_turns(self):
        history = ["User Request: First task in a.py", "Reviewer Decision: APPROVED"]
        compacted, summary = compact_conversation_history(history, max_recent=0)
        self.assertEqual(len(compacted), 1)
        self.assertEqual(compacted[0], summary)
        self.assertIn("a.py", summary)

    def test_history_compactor_class(self):
        compactor = HistoryCompactor(max_recent=2, max_summary_chars=300)
        history = [f"User Request: Step {i} in src/s{i}.py" for i in range(5)]
        compacted, summary = compactor.compact(history)
        self.assertEqual(len(compacted), 3)
        self.assertEqual(compacted[1:], history[-2:])
        self.assertLessEqual(len(summary), 300)
        self.assertIn("src/s0.py", summary)

    def test_task_context_history_summary_roundtrip(self):
        ctx = TaskContext(
            task="Add caching",
            task_name="add-caching",
            repo_path=".",
            history_summary="Compacted history summary (2 earlier turns):\n- User request: Init",
        )
        serialized = ctx.to_dict()
        self.assertEqual(serialized["history_summary"], ctx.history_summary)

        restored = TaskContext.from_dict(serialized)
        self.assertEqual(restored.history_summary, ctx.history_summary)

        legacy_data = {
            "task": "Legacy task",
            "task_name": "legacy-task",
            "repo_path": ".",
        }
        legacy_restored = TaskContext.from_dict(legacy_data)
        self.assertEqual(legacy_restored.history_summary, "")

    def test_build_agent_payload_compaction_and_short_passthrough(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            orch = Orchestrator(repo_path=temp_dir, allowed_directory=".")
            ctx = TaskContext(
                task="Add OAuth",
                task_name="add-oauth",
                repo_path=temp_dir,
                allowed_directory=".",
            )

            # Short history passes through unchanged with empty history_summary
            orch.conversation_history = [
                "User Request: Setup repo",
                "Reviewer Decision: APPROVED",
            ]
            short_payload = build_agent_payload(orch, ctx, model_name="GEMMA (LOCAL)")
            self.assertEqual(short_payload["history"], orch.conversation_history)
            self.assertEqual(ctx.history_summary, "")
            self.assertEqual(short_payload["context"]["history_summary"], "")

            # Long history compacts older turns and updates task_context.history_summary
            orch.conversation_history = [
                "User Request: Create auth module in src/auth.py",
                "Planner Implementation Steps:\n1. Create src/auth.py",
                "Files Modified/Created: src/auth.py",
                "Reviewer Decision: APPROVED",
                "User Request: Add middleware in src/middleware.py",
                "Reviewer Decision: APPROVED",
            ]
            original_snapshot = list(orch.conversation_history)
            long_payload = build_agent_payload(orch, ctx, model_name="GEMINI (REMOTE)")

            self.assertEqual(orch.conversation_history, original_snapshot)
            self.assertEqual(len(long_payload["history"]), DEFAULT_RECENT_TURNS + 1)
            self.assertEqual(long_payload["history"][1:], original_snapshot[-DEFAULT_RECENT_TURNS:])
            self.assertNotEqual(ctx.history_summary, "")
            self.assertEqual(long_payload["history"][0], ctx.history_summary)
            self.assertEqual(long_payload["context"]["history_summary"], ctx.history_summary)
            self.assertIn("src/auth.py", ctx.history_summary)


if __name__ == "__main__":
    unittest.main()
