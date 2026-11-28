import json
import shutil
import tempfile
import unittest

from maca.agents.coder import SimpleCoderAgent, SpecCoderAgent
from maca.context import TaskContext
from maca.orchestrator import Orchestrator
from maca.stages.common import build_agent_payload
from maca.todo import format_compact_todo, init_todo_file, update_todo_progress


class DummyModelClient:
    def __init__(self, response_text: str = ""):
        self.response_text = response_text
        self.last_prompt = ""
        self.last_system = ""

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        self.last_prompt = prompt
        self.last_system = system_instruction
        return self.response_text


class TestTaskContextCompactDict(unittest.TestCase):
    def setUp(self):
        self.ctx = TaskContext(
            task="Implement auth flow",
            task_name="implement-auth",
            repo_path="/tmp/demo",
            allowed_directory="src",
            complexity="COMPLEX",
            plan="1. Create auth.py\n2. Create tests/test_auth.py",
            spec="# Technical Spec\nDetailed specification body.",
            bootstrap_config={"framework": "FastAPI"},
        )
        self.ctx.update_agent("planner", completed=True, summary="Plan ready")

    def test_to_compact_dict_defaults_match_to_dict(self):
        full = self.ctx.to_dict()
        compact = self.ctx.to_compact_dict()
        self.assertEqual(compact, full)
        self.assertNotIn("plan_omitted", compact)
        self.assertNotIn("spec_omitted", compact)

    def test_to_compact_dict_omits_plan_only(self):
        compact = self.ctx.to_compact_dict(omit_plan=True)
        self.assertNotIn("plan", compact)
        self.assertTrue(compact["plan_omitted"])
        self.assertEqual(compact["plan_chars"], len(self.ctx.plan or ""))
        self.assertEqual(compact["spec"], self.ctx.spec)
        self.assertNotIn("spec_omitted", compact)
        # Full to_dict remains unchanged for task.json persistence
        self.assertEqual(self.ctx.to_dict()["plan"], self.ctx.plan)

    def test_to_compact_dict_omits_spec_only(self):
        compact = self.ctx.to_compact_dict(omit_spec=True)
        self.assertNotIn("spec", compact)
        self.assertTrue(compact["spec_omitted"])
        self.assertEqual(compact["spec_chars"], len(self.ctx.spec or ""))
        self.assertEqual(compact["plan"], self.ctx.plan)
        self.assertNotIn("plan_omitted", compact)
        self.assertEqual(self.ctx.to_dict()["spec"], self.ctx.spec)

    def test_to_compact_dict_omits_both_and_preserves_metadata(self):
        compact = self.ctx.to_compact_dict(omit_plan=True, omit_spec=True)
        self.assertNotIn("plan", compact)
        self.assertNotIn("spec", compact)
        self.assertTrue(compact["plan_omitted"])
        self.assertTrue(compact["spec_omitted"])
        self.assertEqual(compact["plan_chars"], len(self.ctx.plan or ""))
        self.assertEqual(compact["spec_chars"], len(self.ctx.spec or ""))
        self.assertEqual(compact["task"], "Implement auth flow")
        self.assertEqual(compact["task_name"], "implement-auth")
        self.assertEqual(compact["complexity"], "COMPLEX")
        self.assertEqual(compact["bootstrap_config"], {"framework": "FastAPI"})
        self.assertTrue(compact["agent_updates"]["planner"]["completed"])

        restored = TaskContext.from_dict(compact)
        self.assertIsNone(restored.plan)
        self.assertIsNone(restored.spec)
        self.assertEqual(restored.task_name, "implement-auth")

    def test_to_compact_dict_when_plan_and_spec_are_none(self):
        empty_ctx = TaskContext(
            task="Simple task",
            task_name="simple-task",
            repo_path="/tmp/demo",
        )
        compact = empty_ctx.to_compact_dict(omit_plan=True, omit_spec=True)
        self.assertNotIn("plan", compact)
        self.assertNotIn("spec", compact)
        self.assertNotIn("plan_omitted", compact)
        self.assertNotIn("spec_omitted", compact)


class TestBuildAgentPayloadDedup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name, allowed_directory=".")
        self.large_plan = "# Plan\n" + ("1. Build module step\n" * 40)
        self.large_spec = "# Spec\n" + ("Detailed contract requirement.\n" * 60)
        self.ctx = TaskContext(
            task="Build service",
            task_name="build-service",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
            complexity="COMPLEX",
            plan=self.large_plan,
            spec=self.large_spec,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_payload_keeps_full_context_when_plan_and_spec_not_in_kwargs(self):
        payload = build_agent_payload(self.orch, self.ctx, model_name="GEMINI (REMOTE)")
        self.assertEqual(payload["context"], self.ctx.to_dict())

    def test_payload_deduplicates_plan_when_passed_in_kwargs(self):
        payload = build_agent_payload(
            self.orch,
            self.ctx,
            model_name="GEMINI (REMOTE)",
            plan=self.large_plan,
        )
        self.assertEqual(payload["plan"], self.large_plan)
        self.assertNotIn("plan", payload["context"])
        self.assertTrue(payload["context"]["plan_omitted"])
        self.assertEqual(payload["context"]["plan_chars"], len(self.large_plan))
        self.assertEqual(payload["context"]["spec"], self.large_spec)

    def test_payload_deduplicates_plan_and_spec_for_coder(self):
        payload = build_agent_payload(
            self.orch,
            self.ctx,
            model_name="CLAUDE (REMOTE)",
            coder_type="SPEC",
            plan=self.large_plan,
            spec=self.large_spec,
        )
        self.assertEqual(payload["plan"], self.large_plan)
        self.assertEqual(payload["spec"], self.large_spec)
        self.assertNotIn("plan", payload["context"])
        self.assertNotIn("spec", payload["context"])
        self.assertTrue(payload["context"]["plan_omitted"])
        self.assertTrue(payload["context"]["spec_omitted"])

        dedup_size = len(json.dumps(payload))
        duplicated_payload = dict(payload)
        duplicated_payload["context"] = self.ctx.to_dict()
        dup_size = len(json.dumps(duplicated_payload))
        self.assertLess(dedup_size, dup_size)

    def test_payload_deduplicates_both_when_plan_or_spec_passed(self):
        payload = build_agent_payload(
            self.orch,
            self.ctx,
            model_name="CLAUDE (REMOTE)",
            plan_or_spec=self.large_spec,
        )
        self.assertEqual(payload["plan_or_spec"], self.large_spec)
        self.assertNotIn("plan", payload["context"])
        self.assertNotIn("spec", payload["context"])
        self.assertTrue(payload["context"]["plan_omitted"])
        self.assertTrue(payload["context"]["spec_omitted"])

    def test_payload_preserves_context_when_passed_empty_plan_or_spec(self):
        payload = build_agent_payload(
            self.orch,
            self.ctx,
            model_name="GEMMA (LOCAL)",
            plan="",
            spec="",
        )
        self.assertEqual(payload["context"]["plan"], self.large_plan)
        self.assertEqual(payload["context"]["spec"], self.large_spec)


class TestFormatCompactTodo(unittest.TestCase):
    def test_mixed_completed_and_pending(self):
        todo = (
            "# Todo Progress for task: demo (coder)\n"
            "\n"
            "- [x] Create models.py\n"
            "- [X] Create utils.py\n"
            "- [ ] Create api.py\n"
            "- [ ] Write unit tests\n"
        )
        compact = format_compact_todo(todo)
        self.assertIn("# Todo Progress for task: demo (coder)", compact)
        self.assertIn("Completed: 2/4 steps", compact)
        self.assertNotIn("Create models.py", compact)
        self.assertNotIn("Create utils.py", compact)
        self.assertIn("- [ ] Create api.py", compact)
        self.assertIn("- [ ] Write unit tests", compact)

    def test_preserves_section_headings_and_notes(self):
        todo = (
            "# Todo Progress\n"
            "\n"
            "## Backend\n"
            "- [x] Create models.py\n"
            "- [ ] Create api.py\n"
            "\n"
            "## Tests\n"
            "- [x] Create fixture\n"
            "- [ ] Add integration test\n"
            "Note: keep API backwards compatible\n"
        )
        compact = format_compact_todo(todo)
        self.assertIn("# Todo Progress", compact)
        self.assertIn("Completed: 2/4 steps", compact)
        self.assertIn("## Backend", compact)
        self.assertIn("## Tests", compact)
        self.assertIn("- [ ] Create api.py", compact)
        self.assertIn("- [ ] Add integration test", compact)
        self.assertIn("Note: keep API backwards compatible", compact)
        self.assertNotIn("- [x]", compact)
        self.assertNotIn("\n\n\n", compact)

    def test_all_items_done(self):
        todo = (
            "# Todo Progress for task: demo (coder)\n"
            "\n"
            "- [x] Create models.py\n"
            "- [x] Create api.py\n"
        )
        compact = format_compact_todo(todo)
        self.assertIn("# Todo Progress for task: demo (coder)", compact)
        self.assertIn("Completed: 2/2 steps (all steps complete)", compact)
        self.assertNotIn("- [x]", compact)

    def test_none_done(self):
        todo = (
            "# Todo Progress for task: demo (coder)\n"
            "\n"
            "- [ ] Create models.py\n"
            "- [ ] Create api.py\n"
        )
        compact = format_compact_todo(todo)
        self.assertEqual(compact, todo.strip())
        self.assertNotIn("Completed:", compact)

    def test_no_checklist_items(self):
        todo = "# Notes\nPlain progress log with no checkboxes."
        compact = format_compact_todo(todo)
        self.assertEqual(compact, todo)

    def test_empty_and_whitespace(self):
        self.assertEqual(format_compact_todo(""), "")
        self.assertEqual(format_compact_todo("   \n\t\n  "), "")

    def test_min_completed_to_collapse_threshold(self):
        todo = "# Todo\n- [x] Step 1\n- [ ] Step 2\n"
        kept = format_compact_todo(todo, min_completed_to_collapse=2)
        self.assertIn("- [x] Step 1", kept)
        self.assertIn("- [ ] Step 2", kept)

        collapsed = format_compact_todo(todo, min_completed_to_collapse=1)
        self.assertIn("Completed: 1/2 steps", collapsed)
        self.assertNotIn("- [x] Step 1", collapsed)
        self.assertIn("- [ ] Step 2", collapsed)


class TestCoderContinuationPromptCompaction(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_simple_coder_compacts_completed_items_on_nudge(self):
        client = DummyModelClient("Mock response")
        agent = SimpleCoderAgent("SimpleCoder", client, repo_path=self.test_dir)
        plan = (
            "1. Implement step1.py\n"
            "2. Implement step2.py\n"
            "3. Implement step3.py\n"
            "4. Implement step4.py"
        )
        init_todo_file(self.test_dir, "compact-task", "coder", plan)
        update_todo_progress(
            self.test_dir,
            "compact-task",
            "coder",
            generated_files={
                "step1.py": "a = 1",
                "step2.py": "b = 2",
                "step3.py": "c = 3",
            },
        )

        agent.run(
            task_description="Finish multi-step task",
            plan=plan,
            task_name="compact-task",
            nudge="Please complete step4.py",
        )

        self.assertIn("Completed: 3/5 steps", client.last_prompt)
        self.assertNotIn("- [x] Implement step1.py", client.last_prompt)
        self.assertNotIn("- [x] Implement step2.py", client.last_prompt)
        self.assertNotIn("- [x] Implement step3.py", client.last_prompt)
        self.assertIn("- [ ] Implement step4.py", client.last_prompt)
        self.assertIn("- [ ] Nudge requirement: Please complete step4.py", client.last_prompt)
        self.assertIn(
            "CONTINUATION INSTRUCTION: Items marked [x] are ALREADY COMPLETED. Do NOT start over.",
            client.last_prompt,
        )

    def test_spec_coder_compacts_completed_items_on_nudge(self):
        client = DummyModelClient("Mock response")
        agent = SpecCoderAgent("SpecCoder", client, repo_path=self.test_dir)
        spec = "1. Build alpha.py\n2. Build beta.py\n3. Build gamma.py"
        init_todo_file(self.test_dir, "spec-compact", "coder", spec)
        update_todo_progress(
            self.test_dir,
            "spec-compact",
            "coder",
            generated_files={"alpha.py": "x = 1", "beta.py": "y = 2"},
        )

        agent.run(
            task_description="Finish spec task",
            spec=spec,
            task_name="spec-compact",
            nudge="Implement gamma.py",
        )

        self.assertIn("Completed: 2/4 steps", client.last_prompt)
        self.assertNotIn("- [x] Build alpha.py", client.last_prompt)
        self.assertNotIn("- [x] Build beta.py", client.last_prompt)
        self.assertIn("- [ ] Build gamma.py", client.last_prompt)
        self.assertIn("- [ ] Nudge requirement: Implement gamma.py", client.last_prompt)

    def test_coder_preserves_single_completed_item(self):
        client = DummyModelClient("Mock response")
        agent = SimpleCoderAgent("SimpleCoder", client, repo_path=self.test_dir)
        plan = "1. Implement alpha.py\n2. Implement beta.py"
        init_todo_file(self.test_dir, "single-done", "coder", plan)
        update_todo_progress(
            self.test_dir,
            "single-done",
            "coder",
            generated_files={"alpha.py": "x = 1"},
        )

        agent.run(
            task_description="Finish beta",
            plan=plan,
            task_name="single-done",
            nudge="Finish beta.py",
        )

        self.assertIn("- [x] Implement alpha.py", client.last_prompt)
        self.assertIn("- [ ] Implement beta.py", client.last_prompt)


if __name__ == "__main__":
    unittest.main()
