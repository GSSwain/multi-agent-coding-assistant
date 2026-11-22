import tempfile
import unittest
from unittest import mock

from maca.context import TaskContext
from maca.orchestrator import Orchestrator
from maca.pipeline import WorkflowPipeline


class TestWorkflowPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name)
        self.pipeline = WorkflowPipeline(self.orch)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pipeline_init(self):
        self.assertEqual(self.pipeline.orch, self.orch)

    def test_build_agent_payload(self):
        ctx = TaskContext(
            task="Do feature",
            task_name="do-feature",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )
        payload = self.pipeline._build_agent_payload(ctx, "GEMMA (LOCAL)", custom_key="value")
        self.assertEqual(payload["task_name"], "do-feature")
        self.assertEqual(payload["task_description"], "Do feature")
        self.assertEqual(payload["model_name"], "GEMMA (LOCAL)")
        self.assertEqual(payload["custom_key"], "value")

    def test_collect_repo_files_content(self):
        self.orch.workspace.write_file("main.py", "print('hello')")
        self.orch.workspace.write_file("utils.py", "def helper(): pass")
        self.orch.workspace.write_file("other.py", "ignore me")

        content = self.pipeline._collect_repo_files_content(
            ["main.py", "utils.py", "other.py"],
            plan="1. Update main.py",
            spec="Spec references utils.py",
        )
        self.assertIn("main.py", content)
        self.assertIn("utils.py", content)
        self.assertNotIn("other.py", content)

    def test_spec_cancelled_by_user(self):
        ctx = TaskContext(
            task="Build feature",
            task_name="build-feature",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )
        with (
            mock.patch("maca.orchestrator.SpecAgent") as mock_spec_cls,
            mock.patch("maca.orchestrator.Prompt.ask", return_value="/cancel"),
        ):
            mock_spec = mock_spec_cls.return_value
            mock_spec.run.return_value = "Spec content"
            spec = self.pipeline._spec_task(
                task_description="Build feature",
                plan="1. Plan",
                complexity="MEDIUM",
                client=None,
                model_name="GEMMA",
                task_context=ctx,
            )
            self.assertIsNone(spec)


if __name__ == "__main__":
    unittest.main()
