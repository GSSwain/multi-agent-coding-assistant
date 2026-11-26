import os
import shutil
import tempfile
import unittest

from maca.agents.coder import SimpleCoderAgent
from maca.context import TaskContext
from maca.orchestrator import Orchestrator
from maca.workspace import WorkspaceManager


class DummyModelClient:
    def __init__(self, response_text: str = ""):
        self.response_text = response_text
        self.last_prompt = ""
        self.last_system = ""

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        self.last_prompt = prompt
        self.last_system = system_instruction
        return self.response_text


class TestTaskContext(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "src", "sub"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "outside"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_context_initialization_and_serialization(self):
        ctx = TaskContext(
            task="Add authentication middleware",
            task_name="add-auth-middleware",
            repo_path=self.test_dir,
            allowed_directory="src",
            complexity="MEDIUM",
            bootstrap_config={"framework": "Spring Boot", "build_tool": "Maven"},
        )
        ctx.update_agent(
            "task_classifier",
            completed=True,
            summary="Classified as MEDIUM",
            details={"complexity": "MEDIUM"},
        )
        ctx_dict = ctx.to_dict()

        self.assertEqual(ctx_dict["task"], "Add authentication middleware")
        self.assertEqual(ctx_dict["complexity"], "MEDIUM")
        self.assertEqual(ctx_dict["repo_path"], self.test_dir)
        self.assertEqual(ctx_dict["allowed_directory"], "src")
        self.assertEqual(ctx_dict["bootstrap_config"]["framework"], "Spring Boot")
        self.assertTrue(ctx_dict["agent_updates"]["task_classifier"]["completed"])

        # Deserialize back
        restored = TaskContext.from_dict(ctx_dict)
        self.assertEqual(restored.task, ctx.task)
        self.assertEqual(restored.allowed_directory, "src")
        self.assertEqual(restored.bootstrap_config["build_tool"], "Maven")
        self.assertEqual(
            restored.agent_updates["task_classifier"]["summary"], "Classified as MEDIUM"
        )

    def test_context_is_path_under_allowed_directory(self):
        ctx = TaskContext(
            task="Test task",
            task_name="test-task",
            repo_path=self.test_dir,
            allowed_directory="src",
        )
        self.assertTrue(ctx.is_path_under_allowed_directory("src/auth.py"))
        self.assertTrue(ctx.is_path_under_allowed_directory("src/sub/deep.py"))
        self.assertFalse(ctx.is_path_under_allowed_directory("outside/file.py"))
        self.assertFalse(ctx.is_path_under_allowed_directory("../escape.py"))

    def test_agent_checks_allowed_directory_on_read_write(self):
        client = DummyModelClient("Mock response")
        agent = SimpleCoderAgent(
            "SimpleCoder", client, repo_path=self.test_dir, allowed_directory="src"
        )

        # Reading inside allowed_directory succeeds
        agent.write_file("src/sub/test.txt", "allowed content")
        read_ok = agent.read_file("src/sub/test.txt")
        self.assertEqual(read_ok, "allowed content")

        # Reading outside allowed_directory is blocked (allowed_directory is only for reading)
        agent.write_file("outside/secret.txt", "some content")
        read_fail = agent.read_file("outside/secret.txt")
        self.assertIn("Error:", read_fail)
        self.assertIn("outside allowed directory", read_fail)

        # Writing to workspace succeeds even if outside allowed_directory (workspace can be modified)
        write_ok = agent.write_file("outside/custom.txt", "modifiable in workspace")
        self.assertIn("Successfully wrote", write_ok)

        # Writing that escapes workspace is blocked
        write_escape = agent.write_file("../escape.txt", "blocked")
        self.assertIn("escapes repository root", write_escape)

    def test_workspace_manager_enforces_allowed_directory(self):
        ws = WorkspaceManager(self.test_dir, allowed_directory="src")

        # Reading outside allowed directory fails
        ws.write_file("outside/file.py", "content")
        res_read = ws.read_file("outside/file.py")
        self.assertIn("Error: Path outside/file.py is outside allowed directory", res_read)

        # Writing inside workspace succeeds
        res_write = ws.write_file("outside/file.py", "updated content")
        self.assertIn("Successfully wrote", res_write)

        # Writing that escapes workspace fails
        res_escape = ws.write_file("../escape.py", "escape content")
        self.assertIn("escapes repository root", res_escape)

        # apply_changes applies files within workspace
        _, records = ws.apply_changes({"src/ok.py": "x=1", "outside/ok2.py": "y=2"})
        actions = {r["path"]: r["action"] for r in records}
        self.assertEqual(actions["src/ok.py"], "Created")
        self.assertEqual(actions["outside/ok2.py"], "Created")

    def test_staging_lifecycle(self):
        ws = WorkspaceManager(repo_path=self.test_dir, allowed_directory="src")
        task_name = "staging-test"

        # 1. Flush files to staging
        count, records = ws.flush_to_staging(
            task_name, {"src/staged.py": "alpha = 1", "docs/notes.md": "notes"}
        )
        self.assertEqual(count, 2)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r["safe"] for r in records))

        # 2. Workspace root remains untouched
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "src/staged.py")))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "docs/notes.md")))

        # 3. List and read staged files
        staged_files = ws.list_staging_files(task_name)
        self.assertEqual(staged_files, ["docs/notes.md", "src/staged.py"])
        self.assertEqual(ws.read_staging_file(task_name, "src/staged.py"), "alpha = 1")
        self.assertEqual(ws.read_staging_file(task_name, "docs/notes.md"), "notes")

        # 4. Attempting path traversal in staging is blocked
        esc_count, esc_records = ws.flush_to_staging(task_name, {"../../outside.py": "evil"})
        self.assertEqual(esc_count, 0)
        self.assertIn("Failed", esc_records[0]["action"])

        # 5. Promote staging files to workspace (moves files and removes staging dir)
        promoted_count, _ = ws.promote_staging_files(task_name)
        self.assertEqual(promoted_count, 2)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "src/staged.py")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "docs/notes.md")))
        self.assertEqual(ws.read_file("src/staged.py"), "alpha = 1")
        self.assertFalse(os.path.exists(ws.get_staging_dir(task_name)))

    def test_coder_prompt_includes_allowed_directory(self):
        client = DummyModelClient("Mock response")
        coder = SimpleCoderAgent(
            "SimpleCoder", client, repo_path=self.test_dir, allowed_directory="src/components"
        )

        coder.run(
            task_description="Implement feature",
            plan="1. Edit a.py",
            task_name="test-task",
            allowed_directory="src/components",
        )

        self.assertIn("Allowed Reading Directory: src/components", client.last_prompt)
        self.assertIn("Workspace Modification Boundary", client.last_prompt)

    def test_summary_formatter(self):
        ctx = TaskContext(
            task="Add login endpoint",
            task_name="add-login",
            repo_path=self.test_dir,
            allowed_directory="src",
            complexity="SIMPLE",
        )
        ctx.update_agent("task_classifier", completed=True, summary="Evaluated as SIMPLE")
        summary = ctx.format_summary()

        self.assertIn("=== Task Context: add-login ===", summary)
        self.assertIn("Allowed Directory (Read-Only): src", summary)
        self.assertIn("Workspace (Modifiable):", summary)
        self.assertIn("[task_classifier]: COMPLETED - Evaluated as SIMPLE", summary)

    def test_orchestrator_initializes_with_allowed_directory(self):
        orch = Orchestrator(repo_path=self.test_dir, allowed_directory="src/subdir")
        self.assertEqual(orch.allowed_directory, "src/subdir")
        self.assertEqual(orch.workspace.allowed_directory, "src/subdir")

    def test_symlink_traversal_blocked(self):
        ws = WorkspaceManager(repo_path=self.test_dir, allowed_directory="src")
        external_dir = tempfile.mkdtemp()
        try:
            external_secret = os.path.join(external_dir, "secret.txt")
            with open(external_secret, "w", encoding="utf-8") as f:
                f.write("top secret")

            symlink_path = os.path.join(self.test_dir, "src", "ext_link")
            try:
                os.symlink(external_dir, symlink_path)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"Symlinks not supported in this environment: {exc}")

            self.assertFalse(ws.is_path_safe(os.path.join(symlink_path, "secret.txt")))
            self.assertIn("escapes repository root", ws.read_file("src/ext_link/secret.txt"))
            self.assertIn("escapes repository root", ws.write_file("src/ext_link/hack.txt", "bad"))
        finally:
            shutil.rmtree(external_dir, ignore_errors=True)

    def test_generate_task_slug_disambiguation(self):
        # Short tasks keep clean human-readable names
        self.assertEqual(WorkspaceManager.generate_task_slug("Add login"), "add-login")

        # Long tasks sharing the first 30 characters get unique hashed slugs <= 30 chars
        task_a = "Create a simple greeting function in greet_alpha.py"
        task_b = "Create a simple greeting function in greet_beta.py"
        slug_a = WorkspaceManager.generate_task_slug(task_a)
        slug_b = WorkspaceManager.generate_task_slug(task_b)
        self.assertNotEqual(slug_a, slug_b)
        self.assertLessEqual(len(slug_a), 30)
        self.assertLessEqual(len(slug_b), 30)

    def test_cleanup_tasks(self):
        ws = WorkspaceManager(repo_path=self.test_dir, allowed_directory=".")
        ws.flush_to_staging("task-one", {"a.py": "x = 1"})
        ws.record_task_progress("task-one", "code_staged", {"status": "STAGED"})

        staging_dir = ws.get_staging_dir("task-one")
        task_dir = os.path.dirname(staging_dir)
        self.assertTrue(os.path.exists(staging_dir))

        # 1. Clean staging only preserves task metadata (task.json, progress.md)
        count, removed = ws.cleanup_tasks(staging_only=True)
        self.assertEqual(count, 1)
        self.assertFalse(os.path.exists(staging_dir))
        self.assertTrue(os.path.exists(os.path.join(task_dir, "task.json")))

        # 2. Full cleanup removes the task directory
        count_all, _ = ws.cleanup_tasks(staging_only=False)
        self.assertEqual(count_all, 1)
        self.assertFalse(os.path.exists(task_dir))


if __name__ == "__main__":
    unittest.main()
