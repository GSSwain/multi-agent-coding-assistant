import os
import tempfile
import unittest
from unittest import mock

from maca.context import TaskContext
from maca.orchestrator import Orchestrator
from maca.stages.review import ReviewStage


class TestStageReview(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name, allowed_directory=".")
        self.stage = ReviewStage(self.orch)
        self.ctx = TaskContext(
            task="Refactor pipeline",
            task_name="refactor-pipeline",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_persist_pre_review(self):
        generated_files = {"service.py": "class Service: pass"}
        file_blocks = {"service.py": [{"start_line": 1, "end_line": 1, "tag": "created"}]}

        self.stage.persist_pre_review(generated_files, file_blocks, self.ctx)

        # Workspace remains clean until approval and promotion
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir.name, "service.py")))

        # Staged files exist in .maca/<task>/staging
        staging_dir = self.orch.workspace.get_staging_dir(self.ctx.task_name)
        staged_file = os.path.join(staging_dir, "service.py")
        self.assertTrue(os.path.exists(staged_file))
        with open(staged_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "class Service: pass")

        # Promoting stages moves files to real workspace and removes staging directory
        written_count, _ = self.orch.workspace.promote_staging_files(self.ctx.task_name)
        self.assertEqual(written_count, 1)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, "service.py")))
        self.assertEqual(self.orch.workspace.read_file("service.py"), "class Service: pass")
        self.assertFalse(os.path.exists(staging_dir))

    def test_run_reviewer_step_mock(self):
        with mock.patch("maca.orchestrator.ReviewerAgent") as mock_rev_cls:
            mock_rev = mock_rev_cls.return_value
            mock_rev.run.return_value = "APPROVED. Excellent work."
            mock_rev.is_approved.return_value = True
            mock_rev.parse_files.return_value = {"service.py": "class Service: pass"}

            response, is_approved, reviewed_files = self.stage.run_reviewer_step(
                client=None,
                task_description="Refactor pipeline",
                spec="Spec",
                generated_files={"service.py": "code"},
                file_blocks={},
                model_name="GEMMA",
                task_context=self.ctx,
            )
            self.assertTrue(is_approved)
            self.assertIn("APPROVED", response)
            self.assertEqual(reviewed_files, {"service.py": "class Service: pass"})

    def test_reviewer_loop_approved_immediately(self):
        with mock.patch.object(
            self.stage,
            "run_reviewer_step",
            return_value=("APPROVED", True, {"service.py": "final code"}),
        ):
            is_approved, reviewed_files = self.stage.reviewer_loop(
                client=None,
                task_description="Refactor pipeline",
                plan="Plan",
                spec="Spec",
                generated_files={"service.py": "code"},
                file_blocks={},
                repo_files_content={},
                coder_type="SIMPLE",
                model_name="GEMMA",
                task_context=self.ctx,
            )
            self.assertTrue(is_approved)
            self.assertEqual(reviewed_files, {"service.py": "final code"})
            self.assertTrue(self.ctx.agent_updates["reviewer"]["completed"])

    def test_reviewer_loop_with_nudge(self):
        step_returns = [
            ("Issues found: missing docstring", False, {}),
            ("APPROVED with docstring", True, {"service.py": '"""Doc."""\ncode'}),
        ]
        mock_coder = mock.MagicMock(
            return_value=({"service.py": '"""Doc."""\ncode'}, {}, "coder response")
        )
        mock_apply = mock.MagicMock(return_value={"service.py": []})

        with mock.patch.object(self.stage, "run_reviewer_step", side_effect=step_returns):
            is_approved, reviewed_files = self.stage.reviewer_loop(
                client=None,
                task_description="Refactor pipeline",
                plan="Plan",
                spec="Spec",
                generated_files={"service.py": "code"},
                file_blocks={},
                repo_files_content={},
                coder_type="SIMPLE",
                model_name="GEMMA",
                task_context=self.ctx,
                run_coder_fn=mock_coder,
                apply_coder_update_fn=mock_apply,
            )
            self.assertTrue(is_approved)
            mock_coder.assert_called_once()
            mock_apply.assert_called_once()


if __name__ == "__main__":
    unittest.main()
