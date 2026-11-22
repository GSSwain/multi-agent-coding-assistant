import os
import tempfile
import unittest
from unittest import mock

from maca.context import TaskContext
from maca.orchestrator import Orchestrator
from maca.stages.planning import PlanningStage


class TestStagePlanning(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name, allowed_directory=".")
        self.stage = PlanningStage(self.orch)
        self.ctx = TaskContext(
            task="Add login endpoint",
            task_name="add-login",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_classify_task(self):
        with mock.patch.object(self.orch.evaluator, "evaluate", return_value="MEDIUM"):
            complexity = self.stage.classify_task("Add login endpoint", self.ctx)
            self.assertEqual(complexity, "MEDIUM")
            self.assertEqual(self.ctx.complexity, "MEDIUM")
            self.assertTrue(self.ctx.agent_updates["task_classifier"]["completed"])

    def test_plan_task(self):
        with mock.patch("maca.orchestrator.PlannerAgent") as mock_planner_cls:
            mock_planner = mock_planner_cls.return_value
            mock_planner.run.return_value = "1. Setup routes\n2. Add controller"
            mock_planner.list_files.return_value = ["app.py"]

            plan, repo_files = self.stage.plan_task(
                task_description="Add login endpoint",
                task_context=self.ctx,
                client=None,
                model_name="GEMMA",
            )
            self.assertEqual(plan, "1. Setup routes\n2. Add controller")
            self.assertEqual(repo_files, ["app.py"])
            self.assertEqual(self.ctx.plan, plan)
            self.assertTrue(self.ctx.agent_updates["planner"]["completed"])
            self.assertTrue(
                os.path.exists(os.path.join(self.temp_dir.name, ".maca", "add-login", "plan.md"))
            )

    def test_spec_task_skipped_for_simple(self):
        spec = self.stage.spec_task(
            task_description="Add simple helper",
            plan="1. Edit helper.py",
            complexity="SIMPLE",
            client=None,
            model_name="GEMMA",
            task_context=self.ctx,
        )
        self.assertEqual(spec, "1. Edit helper.py")
        self.assertEqual(self.ctx.spec, "1. Edit helper.py")

    def test_spec_task_cancelled_by_user(self):
        with (
            mock.patch("maca.orchestrator.SpecAgent") as mock_spec_cls,
            mock.patch("maca.orchestrator.Prompt.ask", return_value="/cancel"),
        ):
            mock_spec = mock_spec_cls.return_value
            mock_spec.run.return_value = "# Spec for login"

            spec = self.stage.spec_task(
                task_description="Add login endpoint",
                plan="1. Plan",
                complexity="MEDIUM",
                client=None,
                model_name="GEMMA",
                task_context=self.ctx,
            )
            self.assertIsNone(spec)

    def test_spec_task_approved_by_user(self):
        with (
            mock.patch("maca.orchestrator.SpecAgent") as mock_spec_cls,
            mock.patch("maca.orchestrator.Prompt.ask", return_value=""),
        ):
            mock_spec = mock_spec_cls.return_value
            mock_spec.run.return_value = "# Spec for login"
            mock_spec.read_file.return_value = "# Spec for login"

            spec = self.stage.spec_task(
                task_description="Add login endpoint",
                plan="1. Plan",
                complexity="MEDIUM",
                client=None,
                model_name="GEMMA",
                task_context=self.ctx,
            )
            self.assertEqual(spec, "# Spec for login")
            self.assertTrue(self.ctx.agent_updates["spec"]["completed"])
            self.assertTrue(
                os.path.exists(os.path.join(self.temp_dir.name, ".maca", "add-login", "spec.md"))
            )

    def test_clarify_task_spring_boot(self):
        ctx = TaskContext(
            task="Creating a hello world spring boot app",
            task_name="spring-boot-app",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )
        with (
            mock.patch("maca.orchestrator.ClarifierAgent") as mock_clarifier_cls,
            mock.patch("maca.orchestrator.Prompt.ask", return_value=""),
        ):
            mock_clarifier = mock_clarifier_cls.return_value
            mock_clarifier.clarify.return_value = {
                "framework": "Spring Boot",
                "build_tool": "Maven",
                "java_version": "21",
            }
            config = self.stage.clarify_task("Creating a hello world spring boot app", ctx)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config["framework"], "Spring Boot")
        self.assertEqual(config["build_tool"], "Maven")
        self.assertEqual(ctx.bootstrap_config["framework"], "Spring Boot")
        self.assertTrue(ctx.agent_updates["clarifier"]["completed"])

    def test_plan_task_injects_bootstrap_configuration(self):
        ctx = TaskContext(
            task="Creating a hello world spring boot app",
            task_name="spring-boot-app",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
            bootstrap_config={
                "framework": "Spring Boot",
                "build_tool": "Gradle (Kotlin DSL)",
                "java_version": "21",
                "spring_boot_version": "3.3.x",
                "language": "Java",
            },
        )
        with mock.patch("maca.orchestrator.PlannerAgent") as mock_planner_cls:
            mock_planner = mock_planner_cls.return_value
            mock_planner.run.return_value = "1. Setup build.gradle.kts\n2. Add Application.java"
            mock_planner.list_files.return_value = []

            plan, _ = self.stage.plan_task(
                task_description="Creating a hello world spring boot app",
                task_context=ctx,
                client=None,
                model_name="GEMMA",
            )
            # Verify Planner was called with effective task containing Gradle & Spring Boot configuration
            called_task = mock_planner.run.call_args[0][0]
            self.assertIn("[Framework Bootstrap Configuration]", called_task)
            self.assertIn("Gradle", called_task)
            self.assertIn("21", called_task)


if __name__ == "__main__":
    unittest.main()
