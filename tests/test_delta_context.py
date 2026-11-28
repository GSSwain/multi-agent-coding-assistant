import tempfile
import unittest
from unittest import mock

from maca.context import TaskContext
from maca.delta_context import (
    build_delta_file_context,
    build_targeted_diff_context,
    extract_mentioned_files,
    summarize_unchanged_file,
)
from maca.orchestrator import Orchestrator
from maca.stages.coding import CodingStage
from maca.stages.review import ReviewStage


class TestExtractMentionedFiles(unittest.TestCase):
    def test_matches_full_path_and_basename(self):
        candidates = ["src/auth.py", "src/db.py", "README.md"]
        feedback = "Please fix login handling in `auth.py` and check src\\db.py:42."
        mentioned = extract_mentioned_files(feedback, candidates)
        self.assertEqual(mentioned, {"src/auth.py", "src/db.py"})

    def test_case_insensitive_and_punctuation_boundaries(self):
        candidates = ["src/Service.py", "config.json"]
        feedback = "Missing validation in service.py. Also inspect (CONFIG.JSON)."
        mentioned = extract_mentioned_files(feedback, candidates)
        self.assertEqual(mentioned, {"src/Service.py", "config.json"})

    def test_avoids_partial_substring_false_positives(self):
        candidates = ["a.py", "auth.py", "extra.py"]
        feedback = "Please update extra.py and remove auth.pyc and auth.py.bak."
        mentioned = extract_mentioned_files(feedback, candidates)
        self.assertEqual(mentioned, {"extra.py"})

    def test_disambiguates_duplicate_basenames(self):
        candidates = ["pkg_a/utils.py", "pkg_b/utils.py"]
        mentioned_specific = extract_mentioned_files("Fix error in pkg_a/utils.py", candidates)
        self.assertEqual(mentioned_specific, {"pkg_a/utils.py"})

        mentioned_ambiguous = extract_mentioned_files("Fix error in utils.py", candidates)
        self.assertEqual(mentioned_ambiguous, {"pkg_a/utils.py", "pkg_b/utils.py"})

    def test_empty_feedback_or_candidates(self):
        self.assertEqual(extract_mentioned_files("", ["auth.py"]), set())
        self.assertEqual(extract_mentioned_files("   ", ["auth.py"]), set())
        self.assertEqual(extract_mentioned_files("Fix auth.py", []), set())


class TestSummarizeUnchangedFile(unittest.TestCase):
    def test_python_file_extracts_top_level_symbols_only(self):
        content = (
            "class AuthService:\n"
            "    def method(self):\n"
            "        pass\n\n"
            "def login(user):\n"
            "    def inner():\n"
            "        return True\n"
            "    return inner()\n\n"
            "async def refresh_token():\n"
            "    return None\n"
        )
        summary = summarize_unchanged_file("src/auth.py", content)
        self.assertNotIn("\n", summary)
        self.assertEqual(
            summary,
            "# [UNCHANGED SUMMARY: src/auth.py | 11 lines | symbols: AuthService, login, refresh_token]",
        )

    def test_invalid_python_falls_back_to_regex(self):
        content = "class Broken:\n    def bad(:\n\ndef fallback_fn():\n    pass\n"
        summary = summarize_unchanged_file("broken.py", content)
        self.assertIn("Broken", summary)
        self.assertIn("fallback_fn", summary)
        self.assertIn("5 lines", summary)

    def test_non_python_and_empty_file(self):
        non_py = summarize_unchanged_file("notes.txt", "line one\nline two\n")
        self.assertEqual(non_py, "# [UNCHANGED SUMMARY: notes.txt | 2 lines | symbols: none]")

        empty = summarize_unchanged_file("empty.py", "")
        self.assertEqual(empty, "# [UNCHANGED SUMMARY: empty.py | 0 lines | symbols: none]")

    def test_truncates_excess_symbols(self):
        content = "\n".join(f"def fn_{i}():\n    return {i}" for i in range(25))
        summary = summarize_unchanged_file("many.py", content)
        self.assertNotIn("\n", summary)
        self.assertIn("fn_0", summary)
        self.assertIn("fn_19", summary)
        self.assertNotIn("fn_20", summary)
        self.assertIn("(+5 more)", summary)


class TestBuildDeltaFileContext(unittest.TestCase):
    def test_targeted_keeps_mentioned_full_and_summarizes_others(self):
        repo_files = {
            "base.py": "def base_fn():\n    return 0\n",
            "auth.py": "def login():\n    return False\n",
        }
        generated_files = {
            "auth.py": "def login():\n    return True\n",
            "helper.py": "def format_user(u):\n    return str(u)\n",
        }
        delta = build_delta_file_context(
            repo_files,
            generated_files,
            "Fix token validation in auth.py.",
        )

        self.assertEqual(delta["auth.py"], generated_files["auth.py"])
        self.assertTrue(delta["base.py"].startswith("# [UNCHANGED SUMMARY: base.py |"))
        self.assertIn("base_fn", delta["base.py"])
        self.assertTrue(delta["helper.py"].startswith("# [UNCHANGED SUMMARY: helper.py |"))
        self.assertIn("format_user", delta["helper.py"])
        # Ensure original dicts were not mutated
        self.assertEqual(repo_files["auth.py"], "def login():\n    return False\n")

    def test_fallback_when_no_file_mentioned_keeps_generated_full(self):
        repo_files = {
            "base.py": "def base_fn():\n    return 0\n",
            "auth.py": "def login():\n    return False\n",
        }
        generated_files = {
            "auth.py": "def login():\n    return True\n",
            "helper.py": "def format_user(u):\n    return str(u)\n",
        }
        delta = build_delta_file_context(
            repo_files,
            generated_files,
            "Missing error handling and docstrings.",
        )

        self.assertEqual(delta["auth.py"], generated_files["auth.py"])
        self.assertEqual(delta["helper.py"], generated_files["helper.py"])
        self.assertTrue(delta["base.py"].startswith("# [UNCHANGED SUMMARY: base.py |"))

    def test_empty_inputs_return_empty_dict(self):
        self.assertEqual(build_delta_file_context({}, {}, "Fix auth.py"), {})


class TestBuildTargetedDiffContext(unittest.TestCase):
    def test_new_file_returns_full_content(self):
        new_content = "\n".join(f"x_{i} = {i}" for i in range(25))
        result = build_targeted_diff_context("new_mod.py", "", new_content, context_lines=3)
        self.assertEqual(result, new_content)

    def test_small_file_returns_full_content(self):
        old_text = "def a():\n    return 1\n"
        new_text = "def a():\n    return 2\n"
        result = build_targeted_diff_context("small.py", old_text, new_text, context_lines=10)
        self.assertEqual(result, new_text)

    def test_modified_large_file_returns_unified_diff(self):
        old_lines = [f"line_{i} = {i}" for i in range(30)]
        new_lines = list(old_lines)
        new_lines[15] = "line_15 = 999"
        old_content = "\n".join(old_lines)
        new_content = "\n".join(new_lines)

        result = build_targeted_diff_context("big.py", old_content, new_content, context_lines=2)
        self.assertIn("--- a/big.py", result)
        self.assertIn("+++ b/big.py", result)
        self.assertIn("-line_15 = 15", result)
        self.assertIn("+line_15 = 999", result)
        self.assertIn(" line_13 = 13", result)
        self.assertIn(" line_17 = 17", result)
        self.assertNotIn("line_0 = 0", result)
        self.assertNotIn("line_29 = 29", result)

    def test_unchanged_large_file_returns_summary(self):
        content = "\n".join(f"def fn_{i}():\n    return {i}" for i in range(10))
        result = build_targeted_diff_context("same.py", content, content, context_lines=2)
        self.assertTrue(result.startswith("# [UNCHANGED SUMMARY: same.py |"))


class TestDeltaContextStageIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name, allowed_directory=".")
        self.coding_stage = CodingStage(self.orch)
        self.review_stage = ReviewStage(self.orch)
        self.ctx = TaskContext(
            task="Build auth service",
            task_name="build-auth",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_coding_stage_nudge_passes_delta_context(self):
        responses = [
            (False, "Missing logout() implementation in auth.py"),
            (True, "All complete"),
        ]
        repo_files = {"db.py": "def connect():\n    pass\n"}
        generated_files = {
            "auth.py": "def login():\n    pass\n",
            "utils.py": "def slugify(s):\n    return s\n",
        }
        captured_contexts = []

        def fake_run_coder_step(**kwargs):
            captured_contexts.append(kwargs["repo_files_content"])
            return {"auth.py": "def login():\n    pass\n\ndef logout():\n    pass\n"}, {}, "ok"

        with mock.patch.object(self.orch, "_is_coder_done", side_effect=responses):
            with mock.patch.object(
                self.coding_stage, "run_coder_step", side_effect=fake_run_coder_step
            ):
                files, _ = self.coding_stage.completion_verification_loop(
                    client=None,
                    task_description="Build auth",
                    plan="Plan",
                    spec="Spec",
                    generated_files=generated_files,
                    file_blocks={},
                    repo_files_content=repo_files,
                    coder_type="SIMPLE",
                    model_name="GEMMA",
                    task_context=self.ctx,
                )

        self.assertEqual(len(captured_contexts), 1)
        sent = captured_contexts[0]
        self.assertEqual(sent["auth.py"], "def login():\n    pass\n")
        self.assertTrue(sent["db.py"].startswith("# [UNCHANGED SUMMARY: db.py |"))
        self.assertTrue(sent["utils.py"].startswith("# [UNCHANGED SUMMARY: utils.py |"))
        self.assertIn("def logout()", files["auth.py"])

    def test_coding_stage_nudge_fallback_keeps_generated_files_full(self):
        responses = [
            (False, "Missing logout functionality"),
            (True, "All complete"),
        ]
        repo_files = {"db.py": "def connect():\n    pass\n"}
        generated_files = {"auth.py": "def login():\n    pass\n"}
        captured_contexts = []

        def fake_run_coder_step(**kwargs):
            captured_contexts.append(kwargs["repo_files_content"])
            return {"auth.py": "def login():\n    pass\n\ndef logout():\n    pass\n"}, {}, "ok"

        with mock.patch.object(self.orch, "_is_coder_done", side_effect=responses):
            with mock.patch.object(
                self.coding_stage, "run_coder_step", side_effect=fake_run_coder_step
            ):
                self.coding_stage.completion_verification_loop(
                    client=None,
                    task_description="Build auth",
                    plan="Plan",
                    spec="Spec",
                    generated_files=generated_files,
                    file_blocks={},
                    repo_files_content=repo_files,
                    coder_type="SIMPLE",
                    model_name="GEMMA",
                    task_context=self.ctx,
                )

        sent = captured_contexts[0]
        self.assertEqual(sent["auth.py"], "def login():\n    pass\n")
        self.assertTrue(sent["db.py"].startswith("# [UNCHANGED SUMMARY: db.py |"))

    def test_review_stage_nudge_passes_delta_context(self):
        step_returns = [
            ("Please add docstring to Service class in service.py.", False, {}),
            ("APPROVED", True, {"service.py": 'class Service:\n    """Doc."""\n'}),
        ]
        repo_files = {"config.py": "DEBUG = True\n"}
        generated_files = {
            "service.py": "class Service:\n    pass\n",
            "models.py": "class User:\n    pass\n",
        }
        mock_coder = mock.MagicMock(
            return_value=({"service.py": 'class Service:\n    """Doc."""\n'}, {}, "ok")
        )
        mock_apply = mock.MagicMock(return_value={"service.py": []})

        with mock.patch.object(self.review_stage, "run_reviewer_step", side_effect=step_returns):
            is_approved, _ = self.review_stage.reviewer_loop(
                client=None,
                task_description="Refactor pipeline",
                plan="Plan",
                spec="Spec",
                generated_files=generated_files,
                file_blocks={},
                repo_files_content=repo_files,
                coder_type="SIMPLE",
                model_name="GEMMA",
                task_context=self.ctx,
                run_coder_fn=mock_coder,
                apply_coder_update_fn=mock_apply,
            )

        self.assertTrue(is_approved)
        mock_coder.assert_called_once()
        sent = mock_coder.call_args.kwargs["repo_files_content"]
        self.assertEqual(sent["service.py"], "class Service:\n    pass\n")
        self.assertTrue(sent["models.py"].startswith("# [UNCHANGED SUMMARY: models.py |"))
        self.assertTrue(sent["config.py"].startswith("# [UNCHANGED SUMMARY: config.py |"))

    def test_review_stage_nudge_fallback_keeps_generated_files_full(self):
        step_returns = [
            ("Issues found: missing docstrings across the module.", False, {}),
            ("APPROVED", True, {"service.py": 'class Service:\n    """Doc."""\n'}),
        ]
        repo_files = {"config.py": "DEBUG = True\n"}
        generated_files = {"service.py": "class Service:\n    pass\n"}
        mock_coder = mock.MagicMock(
            return_value=({"service.py": 'class Service:\n    """Doc."""\n'}, {}, "ok")
        )
        mock_apply = mock.MagicMock(return_value={"service.py": []})

        with mock.patch.object(self.review_stage, "run_reviewer_step", side_effect=step_returns):
            is_approved, _ = self.review_stage.reviewer_loop(
                client=None,
                task_description="Refactor pipeline",
                plan="Plan",
                spec="Spec",
                generated_files=generated_files,
                file_blocks={},
                repo_files_content=repo_files,
                coder_type="SIMPLE",
                model_name="GEMMA",
                task_context=self.ctx,
                run_coder_fn=mock_coder,
                apply_coder_update_fn=mock_apply,
            )

        self.assertTrue(is_approved)
        sent = mock_coder.call_args.kwargs["repo_files_content"]
        self.assertEqual(sent["service.py"], "class Service:\n    pass\n")
        self.assertTrue(sent["config.py"].startswith("# [UNCHANGED SUMMARY: config.py |"))


if __name__ == "__main__":
    unittest.main()
