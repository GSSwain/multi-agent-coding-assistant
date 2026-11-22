import os
import tempfile
import unittest
from unittest import mock

from maca import maca_config as config
from maca.intent import INTENT_CONTINUE, INTENT_NEW_TASK, IntentClassifier
from maca.main import handle_continue_intent
from maca.orchestrator import Orchestrator
from maca.task_store import TaskStore


class ContinueTaskTests(unittest.TestCase):
    def test_intent_classifier_identifies_continue_prompts(self):
        classifier = IntentClassifier()
        for prompt in [
            "continue",
            "Continue",
            "  CONTINUE. ",
            "resume",
            "continue task",
            "continue previous task",
            "resume where we left off!",
        ]:
            self.assertEqual(classifier.identify(prompt), INTENT_CONTINUE, msg=prompt)

    def test_intent_classifier_does_not_misclassify_coding_prompts(self):
        classifier = IntentClassifier()
        for prompt in [
            "",
            "   ",
            "add a continue button to app.js",
            "write a python loop that uses continue",
            "continue building the REST API in server.py",
        ]:
            self.assertEqual(classifier.identify(prompt), INTENT_NEW_TASK, msg=prompt)

    def test_task_store_isolates_tasks_per_working_directory(self):
        with tempfile.TemporaryDirectory() as dir_a, tempfile.TemporaryDirectory() as dir_b:
            store_a = TaskStore(dir_a)
            store_b = TaskStore(dir_b)

            store_a.create_task(
                "Task in A", task_name="task-in-a", complexity="MEDIUM", now_ts=1000.0
            )
            store_b.create_task(
                "Task in B", task_name="task-in-b", complexity="COMPLEX", now_ts=1005.0
            )

            tasks_a = TaskStore(dir_a).load_tasks()
            tasks_b = TaskStore(dir_b).load_tasks()

            self.assertEqual(len(tasks_a), 1)
            self.assertEqual(tasks_a[0]["task_description"], "Task in A")
            self.assertEqual(len(tasks_b), 1)
            self.assertEqual(tasks_b[0]["task_description"], "Task in B")

    def test_task_store_recent_candidates_within_and_outside_window(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(tmpdir)
            store.create_task("Old task", complexity="SIMPLE", now_ts=1000.0)
            store.create_task("Recent task 1", complexity="MEDIUM", now_ts=2000.0)
            store.create_task("Recent task 2", complexity="COMPLEX", now_ts=2120.0)

            candidates = store.get_recent_candidates(window_minutes=5.0)
            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0]["task_description"], "Recent task 2")
            self.assertEqual(candidates[1]["task_description"], "Recent task 1")

            narrow_candidates = store.get_recent_candidates(window_minutes=1.0)
            self.assertEqual(len(narrow_candidates), 1)
            self.assertEqual(narrow_candidates[0]["task_description"], "Recent task 2")

    def test_task_store_read_only_sandbox_keeps_tasks_in_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_read_only = config.SANDBOX_READ_ONLY
            config.SANDBOX_READ_ONLY = True
            try:
                store = TaskStore(tmpdir)
                created = store.create_task("Read-only task", complexity="SIMPLE", now_ts=1000.0)
                self.assertFalse(os.path.exists(store.store_path))
                self.assertEqual(len(store.load_tasks()), 1)
                self.assertEqual(store.load_tasks()[0]["task_id"], created["task_id"])
            finally:
                config.SANDBOX_READ_ONLY = old_read_only

    def test_handle_continue_intent_no_tasks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(tmpdir)
            with (
                mock.patch.object(orch, "resume_task") as resume_mock,
                mock.patch.object(orch.evaluator, "evaluate") as eval_mock,
            ):
                resumed = handle_continue_intent(orch)

            self.assertFalse(resumed)
            resume_mock.assert_not_called()
            eval_mock.assert_not_called()

    def test_handle_continue_intent_single_recent_task_confirmed_and_cancelled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(tmpdir)
            orch.task_store.create_task("Older task", complexity="SIMPLE", now_ts=1000.0)
            latest = orch.task_store.create_task("Latest task", complexity="MEDIUM", now_ts=2000.0)

            with (
                mock.patch("maca.main.Prompt.ask", return_value="y"),
                mock.patch.object(orch, "resume_task") as resume_mock,
                mock.patch.object(orch.evaluator, "evaluate") as eval_mock,
            ):
                resumed = handle_continue_intent(orch, model_override="gemini")

            self.assertTrue(resumed)
            resume_mock.assert_called_once()
            self.assertEqual(resume_mock.call_args[0][0]["task_id"], latest["task_id"])
            self.assertEqual(resume_mock.call_args[1]["model_override"], "gemini")
            eval_mock.assert_not_called()

            with (
                mock.patch("maca.main.Prompt.ask", return_value="n"),
                mock.patch.object(orch, "resume_task") as resume_mock,
            ):
                resumed_cancelled = handle_continue_intent(orch)

            self.assertFalse(resumed_cancelled)
            resume_mock.assert_not_called()

    def test_handle_continue_intent_multiple_recent_tasks_disambiguation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(tmpdir)
            first = orch.task_store.create_task("Task A", complexity="MEDIUM", now_ts=2000.0)
            orch.task_store.create_task("Task B", complexity="COMPLEX", now_ts=2120.0)

            # Newest-first order: 1 -> Task B, 2 -> Task A. User picks "2".
            with (
                mock.patch("maca.main.Prompt.ask", return_value="2") as prompt_mock,
                mock.patch.object(orch, "resume_task") as resume_mock,
                mock.patch.object(orch.evaluator, "evaluate") as eval_mock,
            ):
                resumed = handle_continue_intent(orch)

            self.assertTrue(resumed)
            prompt_mock.assert_called_once()
            resume_mock.assert_called_once()
            self.assertEqual(resume_mock.call_args[0][0]["task_id"], first["task_id"])
            eval_mock.assert_not_called()

            # User chooses cancel
            with (
                mock.patch("maca.main.Prompt.ask", return_value="cancel"),
                mock.patch.object(orch, "resume_task") as resume_mock,
            ):
                resumed_cancel = handle_continue_intent(orch)

            self.assertFalse(resumed_cancel)
            resume_mock.assert_not_called()

    def test_orchestrator_pause_at_spec_and_resume_skips_complexity_planner_and_spec(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(tmpdir)

            # First run: user cancels at Spec review prompt -> task saved as paused/spec_ready
            with (
                mock.patch.object(orch, "_is_gemini_online", return_value=True),
                mock.patch.object(orch, "_is_claude_online", return_value=False),
                mock.patch.object(orch.evaluator, "evaluate", return_value="MEDIUM"),
                mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"),
                mock.patch.object(orch.pipeline.planning_stage, "clarify_task", return_value=None),
                mock.patch("maca.orchestrator.PlannerAgent") as mock_planner_cls,
                mock.patch("maca.orchestrator.SpecAgent") as mock_spec_cls,
                mock.patch("maca.orchestrator.Prompt.ask", return_value="/cancel"),
            ):
                planner_inst = mock_planner_cls.return_value
                planner_inst.list_files.return_value = []
                planner_inst.run.return_value = "1. Build app.py"

                spec_inst = mock_spec_cls.return_value
                spec_inst.run.return_value = "Spec for app.py"

                orch.run_task("Build app.py")

            saved_tasks = orch.task_store.load_tasks()
            self.assertEqual(len(saved_tasks), 1)
            paused_task = saved_tasks[0]
            self.assertEqual(paused_task["status"], "paused")
            self.assertEqual(paused_task["stage"], "spec_ready")
            self.assertTrue(os.path.exists(os.path.join(tmpdir, paused_task["plan_file"])))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, paused_task["spec_file"])))

            # Resume: classify_task, plan_task, and spec_task must NOT be called
            with (
                mock.patch.object(orch, "_is_gemini_online", return_value=True),
                mock.patch.object(orch, "_is_claude_online", return_value=False),
                mock.patch.object(
                    orch.pipeline.planning_stage,
                    "classify_task",
                    side_effect=AssertionError("should not classify on continue"),
                ),
                mock.patch.object(
                    orch.pipeline.planning_stage,
                    "plan_task",
                    side_effect=AssertionError("should reuse saved plan"),
                ),
                mock.patch.object(
                    orch.pipeline.planning_stage,
                    "spec_task",
                    side_effect=AssertionError("should reuse saved spec"),
                ),
                mock.patch.object(config, "get_gemini_api_key", return_value="fake_key"),
                mock.patch("maca.orchestrator.SpecCoderAgent") as mock_coder_cls,
                mock.patch("maca.orchestrator.ReviewerAgent") as mock_reviewer_cls,
                mock.patch.object(orch, "_is_coder_done", return_value=(True, "Done")),
            ):
                coder_inst = mock_coder_cls.return_value
                coder_inst.run.return_value = "[FILE: app.py]\nprint('hello')\n"
                coder_inst.parse_files.return_value = {"app.py": "print('hello')\n"}

                reviewer_inst = mock_reviewer_cls.return_value
                reviewer_inst.run.return_value = "APPROVED"
                reviewer_inst.parse_files.return_value = {}
                reviewer_inst.is_approved.return_value = True

                orch.resume_task(paused_task)

                coder_inst.run.assert_called_once()
                reviewer_inst.run.assert_called_once()

            updated_tasks = orch.task_store.load_tasks()
            self.assertEqual(updated_tasks[0]["status"], "completed")
            self.assertEqual(updated_tasks[0]["stage"], "completed")
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "app.py")))


if __name__ == "__main__":
    unittest.main()
