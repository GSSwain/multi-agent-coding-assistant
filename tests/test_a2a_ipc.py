import os
import tempfile
import unittest

from maca.a2a_call_helper import call_agent


class TestA2AIPC(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_env = os.environ.get("MOCK_GEMMA_FALLBACK")
        os.environ["MOCK_GEMMA_FALLBACK"] = "true"

    def tearDown(self):
        self.temp_dir.cleanup()
        if self.old_env is not None:
            os.environ["MOCK_GEMMA_FALLBACK"] = self.old_env
        else:
            os.environ.pop("MOCK_GEMMA_FALLBACK", None)

    def test_task_classifier_ipc(self):
        res = call_agent("maca.agents.task_classifier", {"task_description": "Fix typo in README"})
        self.assertEqual(res.get("result"), "SIMPLE")

    def test_planner_ipc(self):
        res = call_agent(
            "maca.agents.planner",
            {"task_description": "Add hello world", "repo_files": [], "history": []},
        )
        self.assertIn("result", res)
        self.assertTrue(len(res["result"]) > 0)

    def test_spec_ipc(self):
        res = call_agent(
            "maca.agents.spec",
            {"task_description": "Build auth system", "plan": "1. Create models", "history": []},
        )
        self.assertIn("result", res)
        self.assertTrue(len(res["result"]) > 0)

    def test_coder_simple_ipc(self):
        res = call_agent(
            "maca.agents.coder",
            {
                "coder_type": "SIMPLE",
                "task_description": "Fix typo",
                "plan": "Edit file",
                "repo_files_content": {},
                "history": [],
            },
        )
        self.assertIn("result", res)
        self.assertIn("files", res)
        self.assertIn("file_blocks", res)

    def test_code_completion_verifier_ipc(self):
        res = call_agent(
            "maca.agents.code_completion_verifier",
            {
                "task_description": "Create sample file",
                "spec": "Sample file spec",
                "generated_files": {"sample.py": "print('hello')"},
            },
        )
        self.assertIn("is_done", res)

    def test_reviewer_ipc(self):
        res = call_agent(
            "maca.agents.reviewer",
            {
                "task_description": "Review sample file",
                "generated_files": {"sample.py": "print('hello')"},
                "file_blocks": {
                    "sample.py": [
                        {"start_line": 1, "end_line": 1, "tag": "created", "code": "print('hello')"}
                    ]
                },
                "history": [],
            },
        )
        self.assertIn("result", res)
        self.assertIn("approved", res)

    def test_ipc_with_structured_context(self):
        ctx = {
            "task": "Implement hello world",
            "task_name": "hello-world",
            "complexity": "SIMPLE",
            "repo_path": self.temp_dir.name,
            "allowed_directory": ".",
            "plan": "1. Create hello.py",
        }
        res = call_agent("maca.agents.planner", {"context": ctx})
        self.assertIn("result", res)
        self.assertEqual(res.get("agent"), "planner")
        self.assertTrue(res.get("completed"))
        self.assertIn("update", res)

    def test_clarifier_ipc(self):
        res = call_agent(
            "maca.agents.clarifier",
            {
                "task_description": "Creating a hello world spring boot app",
                "interactive": False,
            },
        )
        self.assertIn("result", res)
        self.assertEqual(res.get("agent"), "clarifier")
        self.assertTrue(res.get("completed"))
        self.assertIsNotNone(res["result"])
        self.assertEqual(res["result"].get("framework"), "Spring Boot")


if __name__ == "__main__":
    unittest.main()
