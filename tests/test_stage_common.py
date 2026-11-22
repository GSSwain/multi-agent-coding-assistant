import tempfile
import unittest
from unittest import mock

from maca.context import TaskContext
from maca.orchestrator import Orchestrator
from maca.stages.common import (
    _get_orch_attr,
    _is_mock,
    build_agent_payload,
    record_step_progress,
)


class TestStageCommon(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name, allowed_directory=".")
        self.ctx = TaskContext(
            task="Add OAuth",
            task_name="add-oauth",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_is_mock(self):
        fake_mock = mock.MagicMock()
        self.assertTrue(_is_mock(fake_mock))

        class RealClass:
            pass

        self.assertFalse(_is_mock(RealClass()))

        class MockHelper:
            pass

        self.assertTrue(_is_mock(MockHelper()))

    def test_get_orch_attr(self):
        # Existing attribute on orchestrator
        from maca.agents.planner import PlannerAgent

        val = _get_orch_attr("PlannerAgent", fallback=None)
        self.assertEqual(val, PlannerAgent)

        # Non-existing attribute falls back
        fallback_val = _get_orch_attr("NonExistentAttr", fallback="fallback_value")
        self.assertEqual(fallback_val, "fallback_value")

    def test_build_agent_payload(self):
        payload = build_agent_payload(
            self.orch,
            self.ctx,
            model_name="GEMINI (REMOTE)",
            extra_param="custom_value",
        )
        self.assertEqual(payload["task_name"], "add-oauth")
        self.assertEqual(payload["task_description"], "Add OAuth")
        self.assertEqual(payload["model_name"], "GEMINI (REMOTE)")
        self.assertEqual(payload["repo_path"], self.orch.repo_path)
        self.assertEqual(payload["allowed_directory"], ".")
        self.assertEqual(payload["extra_param"], "custom_value")
        self.assertIn("context", payload)

    def test_record_step_progress(self):
        record_step_progress(
            self.orch,
            self.ctx,
            agent_name="planner",
            stage="planning",
            status="COMPLETED",
            summary="Plan generated successfully",
            details={"step_count": 3},
            file_path=".maca/add-oauth/plan.md",
        )
        self.assertTrue(self.ctx.agent_updates["planner"]["completed"])
        self.assertEqual(
            self.ctx.agent_updates["planner"]["summary"], "Plan generated successfully"
        )


if __name__ == "__main__":
    unittest.main()
