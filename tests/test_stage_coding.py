import os
import tempfile
import unittest
from unittest import mock

from maca.context import TaskContext
from maca.orchestrator import Orchestrator
from maca.stages.coding import CodingStage


class TestStageCoding(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name, allowed_directory=".")
        self.stage = CodingStage(self.orch)
        self.ctx = TaskContext(
            task="Build auth service",
            task_name="build-auth",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_collect_repo_files_content(self):
        self.orch.workspace.write_file("auth.py", "def login(): pass")
        self.orch.workspace.write_file("db.py", "def connect(): pass")
        self.orch.workspace.write_file("other.py", "# unused")

        content = self.stage.collect_repo_files_content(
            ["auth.py", "db.py", "other.py"],
            plan="1. Update auth.py",
            spec="Spec details db.py connection",
        )
        self.assertIn("auth.py", content)
        self.assertIn("db.py", content)
        self.assertNotIn("other.py", content)

    def test_run_coder_step_mock(self):
        with mock.patch("maca.orchestrator.SpecCoderAgent") as mock_coder_cls:
            mock_coder = mock_coder_cls.return_value
            mock_coder.run.return_value = "FILE: auth.py\n```python\nprint(1)\n```"
            mock_coder.parse_files.return_value = {"auth.py": "print(1)"}

            files, file_blocks, response = self.stage.run_coder_step(
                coder_type="SPEC",
                task_description="Build auth service",
                plan="Plan",
                spec="Spec",
                repo_files_content={},
                client=None,
                model_name="GEMMA",
                task_context=self.ctx,
            )
            self.assertEqual(files, {"auth.py": "print(1)"})
            self.assertIn("auth.py", file_blocks)
            self.assertEqual(response, "FILE: auth.py\n```python\nprint(1)\n```")

    def test_apply_coder_update(self):
        generated_files = {"existing.py": "x = 1"}
        updated_files = {"new.py": "y = 2"}

        blocks = self.stage.apply_coder_update(
            updated_files=updated_files,
            generated_files=generated_files,
            repo_files_content={},
            task_context=self.ctx,
            summary_label="nudge test",
            persist_changes=True,
        )
        self.assertIn("new.py", generated_files)
        self.assertIn("new.py", blocks)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, "new.py")))

    def test_completion_verification_loop_immediately_done(self):
        with mock.patch.object(self.orch, "_is_coder_done", return_value=(True, "All good")):
            files, blocks = self.stage.completion_verification_loop(
                client=None,
                task_description="Build auth",
                plan="Plan",
                spec="Spec",
                generated_files={"auth.py": "code"},
                file_blocks={"auth.py": []},
                repo_files_content={},
                coder_type="SIMPLE",
                model_name="GEMMA",
                task_context=self.ctx,
            )
            self.assertEqual(files, {"auth.py": "code"})
            self.assertTrue(self.ctx.agent_updates["code_completion_verifier"]["completed"])

    def test_completion_verification_loop_with_nudge(self):
        # 1st attempt: incomplete, 2nd attempt: complete
        responses = [(False, "Missing logout function"), (True, "All complete")]
        with (
            mock.patch.object(self.orch, "_is_coder_done", side_effect=responses),
            mock.patch.object(
                self.stage,
                "run_coder_step",
                return_value=({"auth.py": "code + logout"}, {}, "coder response"),
            ),
        ):
            files, blocks = self.stage.completion_verification_loop(
                client=None,
                task_description="Build auth",
                plan="Plan",
                spec="Spec",
                generated_files={"auth.py": "code"},
                file_blocks={"auth.py": []},
                repo_files_content={},
                coder_type="SIMPLE",
                model_name="GEMMA",
                task_context=self.ctx,
            )
            self.assertEqual(files["auth.py"], "code + logout")
            self.assertTrue(self.ctx.agent_updates["code_completion_verifier"]["completed"])


if __name__ == "__main__":
    unittest.main()
