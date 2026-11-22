import shutil
import tempfile
import unittest

from maca.agents.clarifier import ClarifierAgent
from maca.agents.code_completion_verifier import CodeCompletionVerifierAgent
from maca.agents.coder import SimpleCoderAgent
from maca.agents.planner import PlannerAgent
from maca.agents.reviewer import ReviewerAgent
from maca.agents.spec import SpecAgent
from maca.todo import (
    init_todo_file,
    parse_plan_to_items,
    read_todo_file,
    update_todo_progress,
)


class DummyModelClient:
    def __init__(self, response_text: str = ""):
        self.response_text = response_text
        self.last_prompt = ""
        self.last_system = ""

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        self.last_prompt = prompt
        self.last_system = system_instruction
        return self.response_text


class TestTodoTracking(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_plan_to_items(self):
        plan = (
            "# Plan\n"
            "1. Create foo.py [NEW]\n"
            "2. Modify bar.py [MODIFY]\n"
            "- [ ] Write unit test for foo\n"
            "* Verify documentation\n"
        )
        items = parse_plan_to_items(plan)
        self.assertEqual(len(items), 4)
        self.assertIn("Create foo.py [NEW]", items)
        self.assertIn("Modify bar.py [MODIFY]", items)
        self.assertIn("Write unit test for foo", items)
        self.assertIn("Verify documentation", items)

    def test_init_and_read_todo_file(self):
        content = init_todo_file(
            self.test_dir,
            "my-task",
            "coder",
            "1. Step one in a.py\n2. Step two in b.py",
        )
        self.assertIn("- [ ] Step one in a.py", content)
        self.assertIn("- [ ] Step two in b.py", content)

        read_back = read_todo_file(self.test_dir, "my-task", "coder")
        self.assertEqual(read_back, content)

    def test_update_todo_progress_marks_completed_files(self):
        init_todo_file(
            self.test_dir,
            "task1",
            "coder",
            "1. Implement utils.py\n2. Implement main.py",
        )
        # coder generates utils.py
        updated = update_todo_progress(
            self.test_dir,
            "task1",
            "coder",
            generated_files={"utils.py": "def f(): pass"},
        )
        self.assertIn("- [x] Implement utils.py", updated)
        self.assertIn("- [ ] Implement main.py", updated)

    def test_update_todo_progress_on_nudge_does_not_start_over(self):
        init_todo_file(
            self.test_dir,
            "task1",
            "coder",
            "1. Implement utils.py\n2. Implement main.py",
        )
        # Mark utils.py completed
        update_todo_progress(
            self.test_dir,
            "task1",
            "coder",
            generated_files={"utils.py": "def f(): pass"},
        )

        # Now orchestrator nudges coder with feedback
        nudge_feedback = "You missed handling edge cases in main.py."
        updated = update_todo_progress(
            self.test_dir,
            "task1",
            "coder",
            nudge_feedback=nudge_feedback,
        )

        # Verify completed item is still completed ([x])
        self.assertIn("- [x] Implement utils.py", updated)
        # Pending item is still pending ([ ])
        self.assertIn("- [ ] Implement main.py", updated)
        # Nudge requirement was appended as a new pending item
        self.assertIn(
            "- [ ] Nudge requirement: You missed handling edge cases in main.py.", updated
        )

    def test_coder_prompt_contains_continuation_instruction(self):
        client = DummyModelClient("Mock response")
        agent = SimpleCoderAgent("SimpleCoder", client, repo_path=self.test_dir)

        # Initialize todo with one done, one pending
        init_todo_file(
            self.test_dir,
            "task1",
            "coder",
            "1. Implement utils.py\n2. Implement main.py",
        )
        update_todo_progress(
            self.test_dir,
            "task1",
            "coder",
            generated_files={"utils.py": "def f(): pass"},
        )

        # Run coder with nudge
        agent.run(
            task_description="Implement feature",
            plan="1. Implement utils.py\n2. Implement main.py",
            task_name="task1",
            nudge="Please finish main.py",
        )

        # Prompt must include the todo content and continuation instructions
        self.assertIn(
            "Current Todo Progress Checklist (.maca/<task>/coder.todo):", client.last_prompt
        )
        self.assertIn(
            "CONTINUATION INSTRUCTION: Items marked [x] are ALREADY COMPLETED. Do NOT start over.",
            client.last_prompt,
        )
        self.assertIn("- [x] Implement utils.py", client.last_prompt)
        self.assertIn("- [ ] Implement main.py", client.last_prompt)

    def test_all_agents_write_todo_files(self):
        client = DummyModelClient("YES all steps complete")
        task_name = "test-agent-todos"

        # Planner
        planner = PlannerAgent(client, repo_path=self.test_dir)
        planner.run("Test task", repo_files=[], task_name=task_name)
        planner_todo = read_todo_file(self.test_dir, task_name, "planner")
        self.assertIsNotNone(planner_todo)
        self.assertIn("- [x]", planner_todo)

        # Spec
        spec_agent = SpecAgent(client, repo_path=self.test_dir)
        spec_agent.run("Test task", "Plan", task_name=task_name)
        spec_todo = read_todo_file(self.test_dir, task_name, "spec")
        self.assertIsNotNone(spec_todo)
        self.assertIn("- [x]", spec_todo)

        # Coder
        coder_client = DummyModelClient("[FILE: foo.py]\n```python\nprint('hi')\n```")
        coder = SimpleCoderAgent("SimpleCoder", coder_client, repo_path=self.test_dir)
        coder.run("Test task", plan="1. Create foo.py", task_name=task_name)
        coder_todo = read_todo_file(self.test_dir, task_name, "coder")
        self.assertIsNotNone(coder_todo)
        self.assertIn("foo.py", coder_todo)

        # Verifier
        verifier = CodeCompletionVerifierAgent(client, repo_path=self.test_dir)
        verifier.validate("Test task", "Spec", {"foo.py": "print('hi')"}, task_name=task_name)
        verifier_todo = read_todo_file(self.test_dir, task_name, "code_completion_verifier")
        self.assertIsNotNone(verifier_todo)
        self.assertIn("- [x] All specification steps implemented", verifier_todo)

        # Reviewer
        rev_client = DummyModelClient("Code looks great! APPROVED")
        reviewer = ReviewerAgent(rev_client, repo_path=self.test_dir)
        reviewer.run("Test task", {"foo.py": "print('hi')"}, task_name=task_name)
        reviewer_todo = read_todo_file(self.test_dir, task_name, "reviewer")
        self.assertIsNotNone(reviewer_todo)
        self.assertIn("APPROVED", reviewer_todo)

        # Clarifier
        clarifier_client = DummyModelClient(
            '{"is_bootstrap": true, "framework": "FastAPI", "resolved_params": {"lang": "Python"}, "questions": []}'
        )
        clarifier = ClarifierAgent(clarifier_client, repo_path=self.test_dir)
        clarifier.clarify("Create a FastAPI app", interactive=False, task_name=task_name)
        clarifier_todo = read_todo_file(self.test_dir, task_name, "clarifier")
        self.assertIsNotNone(clarifier_todo)
        self.assertIn("FastAPI", clarifier_todo)


if __name__ == "__main__":
    unittest.main()
