import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

from maca import maca_config as config
from maca.agents.coder import SimpleCoderAgent
from maca.context import TaskContext
from maca.health import BackendHealthService
from maca.jsonrpc.client import JsonRpcClient
from maca.main import _apply_target_input, parse_interactive_command
from maca.models.local_gemma import LocalGemmaClient
from maca.orchestrator import Orchestrator
from maca.stages.coding import CodingStage
from maca.task_store import TaskStore
from maca.todo import init_todo_file, update_todo_progress
from maca.workspace import WorkspaceManager


class TestCrossOsWorkspacePaths(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "src", "pkg"), exist_ok=True)
        self.ws = WorkspaceManager(repo_path=self.test_dir, allowed_directory="src")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normalize_relative_path_handles_windows_and_posix(self):
        self.assertEqual(
            WorkspaceManager.normalize_relative_path("src\\pkg\\mod.py"),
            "src/pkg/mod.py",
        )
        self.assertEqual(
            WorkspaceManager.normalize_relative_path("\\src\\pkg\\mod.py"),
            "src/pkg/mod.py",
        )
        self.assertEqual(
            WorkspaceManager.normalize_relative_path("  /src/pkg/mod.py  "),
            "src/pkg/mod.py",
        )

    def test_windows_style_relative_paths_read_write_and_list(self):
        res = self.ws.write_file("src\\pkg\\mod.py", "def greet():\n    return '✓ café λ'\n")
        self.assertIn("Successfully wrote", res)
        self.assertEqual(
            self.ws.read_file("src\\pkg\\mod.py"),
            "def greet():\n    return '✓ café λ'\n",
        )
        listed = self.ws.list_files()
        self.assertIn("src/pkg/mod.py", listed)

    def test_windows_backslash_traversal_drive_and_unc_blocked(self):
        self.assertIn("escapes repository root", self.ws.write_file("..\\outside.py", "bad"))
        self.assertIn("escapes repository root", self.ws.read_file("..\\outside.py"))
        self.assertIn(
            "escapes repository root",
            self.ws.write_file("\\\\server\\share\\evil.txt", "bad"),
        )
        self.assertIn(
            "escapes repository root",
            self.ws.read_file("\\\\server\\share\\evil.txt"),
        )

        written, records = self.ws.apply_changes(
            {
                "..\\escape.py": "bad",
                "C:\\Windows\\System32\\evil.txt": "bad",
                "\\\\server\\share\\evil.txt": "bad",
                "//server/share/evil.txt": "bad",
                "src\\pkg\\safe.py": "value = 42\n",
            }
        )
        self.assertEqual(written, 1)
        by_path = {rec["path"]: rec for rec in records}
        self.assertFalse(by_path["..\\escape.py"]["safe"])
        self.assertFalse(by_path["C:\\Windows\\System32\\evil.txt"]["safe"])
        self.assertFalse(by_path["\\\\server\\share\\evil.txt"]["safe"])
        self.assertFalse(by_path["//server/share/evil.txt"]["safe"])
        self.assertTrue(by_path["src/pkg/safe.py"]["safe"])
        self.assertEqual(self.ws.read_file("src/pkg/safe.py"), "value = 42\n")

    def test_staging_blocks_windows_escapes_and_normalizes_paths(self):
        task_name = "win-staging"
        staged_count, records = self.ws.flush_to_staging(
            task_name,
            {
                "src\\pkg\\staged.py": "# ✓ staged unicode\nx = 1\n",
                "..\\..\\outside.py": "evil",
                "D:\\outside.py": "evil",
                "\\\\srv\\share\\evil.py": "evil",
            },
        )
        self.assertEqual(staged_count, 1)
        self.assertEqual(len(records), 4)
        self.assertEqual(self.ws.list_staging_files(task_name), ["src/pkg/staged.py"])
        self.assertEqual(
            self.ws.read_staging_file(task_name, "src\\pkg\\staged.py"),
            "# ✓ staged unicode\nx = 1\n",
        )
        self.assertIn(
            "staging escape blocked",
            self.ws.read_staging_file(task_name, "..\\..\\secret.txt"),
        )
        self.assertIn(
            "staging escape blocked",
            self.ws.read_staging_file(task_name, "C:\\Windows\\win.ini"),
        )
        self.assertIn(
            "staging escape blocked",
            self.ws.read_staging_file(task_name, "\\\\srv\\share\\secret.txt"),
        )

        promoted, _ = self.ws.promote_staging_files(task_name)
        self.assertEqual(promoted, 1)
        self.assertEqual(self.ws.read_file("src/pkg/staged.py"), "# ✓ staged unicode\nx = 1\n")

    def test_compute_file_blocks_matches_across_separators(self):
        blocks = self.ws.compute_file_blocks(
            {"src/pkg/app.py": "a = 1\nb = 2\n"},
            existing_contents={"src\\pkg\\app.py": "a = 1\nb = 0\n"},
        )
        self.assertIn("src/pkg/app.py", blocks)
        self.assertEqual(blocks["src/pkg/app.py"][0]["tag"], "replace")

    def test_utf8_unicode_roundtrip_task_store_and_progress(self):
        unicode_desc = "Implement ✓ café λ handler — 日本語"
        meta_path = self.ws.record_task_progress(
            "unicode-task",
            "coded",
            {"status": "COMPLETED", "files": ["src/pkg/mod.py"]},
            task_description=unicode_desc,
        )
        self.assertTrue(os.path.exists(meta_path))
        with open(meta_path, "r", encoding="utf-8") as handle:
            meta_data = json.load(handle)
        self.assertEqual(meta_data["task_description"], unicode_desc)

        progress_md_path = os.path.join(os.path.dirname(meta_path), "progress.md")
        with open(progress_md_path, "r", encoding="utf-8") as handle:
            self.assertIn(unicode_desc, handle.read())

        store = TaskStore(self.test_dir)
        created = store.create_task(unicode_desc, task_name="unicode-task")
        loaded = store.load_tasks()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["task_id"], created["task_id"])
        self.assertEqual(loaded[0]["task_description"], unicode_desc)

    def test_context_agent_coding_stage_and_todo_handle_windows_paths(self):
        ctx = TaskContext(
            task="Test",
            task_name="test-win",
            repo_path=self.test_dir,
            allowed_directory="src",
        )
        self.assertTrue(ctx.is_path_under_allowed_directory("src\\pkg\\a.py"))
        self.assertFalse(ctx.is_path_under_allowed_directory("..\\escape.py"))
        self.assertFalse(ctx.is_path_under_allowed_directory("\\\\srv\\share\\a.py"))
        self.assertFalse(ctx.is_path_in_workspace("\\\\srv\\share\\a.py"))

        coder = SimpleCoderAgent(
            "SimpleCoder", mock.MagicMock(), repo_path=self.test_dir, allowed_directory="src"
        )
        crlf_response = "[FILE: src/pkg/crlf.py]\r\n```python\r\nx = 1\r\n```\r\n"
        parsed = coder.parse_files(crlf_response)
        self.assertEqual(parsed, {"src/pkg/crlf.py": "x = 1"})
        self.assertIn("escapes repository root", coder.write_file("..\\escape.py", "bad"))
        self.assertIn("escapes repository root", coder.write_file("\\\\srv\\share\\x.py", "bad"))

        orch = Orchestrator(repo_path=self.test_dir, allowed_directory="src")
        orch.workspace.write_file("src/pkg/utils.py", "def helper():\n    return True\n")
        stage = CodingStage(orch)
        collected = stage.collect_repo_files_content(
            ["src\\pkg\\utils.py"],
            plan="1. Update src/pkg/utils.py",
            spec="",
        )
        self.assertIn("src\\pkg\\utils.py", collected)

        init_todo_file(self.test_dir, "win-todo", "coder", "1. Update src/pkg/utils.py")
        updated_todo = update_todo_progress(
            self.test_dir,
            "win-todo",
            "coder",
            generated_files={"src\\pkg\\utils.py": "def helper(): pass"},
        )
        self.assertIn("- [x] Update src/pkg/utils.py", updated_todo)


class TestCrossOsSubprocessAndHealth(unittest.TestCase):
    def test_health_check_uses_tasklist_on_windows(self):
        cli_fail = subprocess.CompletedProcess(
            args=["ollama", "list"], returncode=1, stdout="", stderr="not found"
        )
        tasklist_ok = subprocess.CompletedProcess(
            args=["tasklist"],
            returncode=0,
            stdout="ollama.exe                    1234 Console                    1     45,000 K\n",
            stderr="",
        )
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused"))
            )
            stack.enter_context(mock.patch("shutil.which", return_value=None))
            stack.enter_context(mock.patch.object(sys, "platform", "win32"))
            mock_run = stack.enter_context(
                mock.patch("subprocess.run", side_effect=[cli_fail, tasklist_ok])
            )
            status = BackendHealthService.check_backends_status(run_handshakes=False)

        self.assertIn("ONLINE (Ollama Running", status["Gemma"])
        self.assertEqual(mock_run.call_count, 2)
        second_args = mock_run.call_args_list[1].args[0]
        second_kwargs = mock_run.call_args_list[1].kwargs
        self.assertEqual(second_args[0], "tasklist")
        self.assertEqual(second_kwargs.get("encoding"), "utf-8")

    def test_health_check_uses_pgrep_on_linux(self):
        cli_fail = subprocess.CompletedProcess(
            args=["ollama", "list"], returncode=1, stdout="", stderr=""
        )
        pgrep_ok = subprocess.CompletedProcess(
            args=["pgrep", "-af", "ollama"],
            returncode=0,
            stdout="1234 ollama serve\n",
            stderr="",
        )
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused"))
            )
            stack.enter_context(mock.patch("shutil.which", return_value=None))
            stack.enter_context(mock.patch.object(sys, "platform", "linux"))
            mock_run = stack.enter_context(
                mock.patch("subprocess.run", side_effect=[cli_fail, pgrep_ok])
            )
            status = BackendHealthService.check_backends_status(run_handshakes=False)

        self.assertIn("ONLINE (Ollama Running", status["Gemma"])
        second_args = mock_run.call_args_list[1].args[0]
        second_kwargs = mock_run.call_args_list[1].kwargs
        self.assertEqual(second_args[0], "pgrep")
        self.assertEqual(second_kwargs.get("encoding"), "utf-8")

    def test_local_gemma_cli_fallback_uses_utf8_and_which(self):
        old_mock = config.MOCK_GEMMA_FALLBACK
        config.MOCK_GEMMA_FALLBACK = False
        cli_ok = subprocess.CompletedProcess(
            args=["/opt/bin/ollama", "run", "gemma2:2b"],
            returncode=0,
            stdout="✓ generated response\n",
            stderr="",
        )
        try:
            client = LocalGemmaClient()
            with ExitStack() as stack:
                stack.enter_context(
                    mock.patch("urllib.request.urlopen", side_effect=OSError("offline"))
                )
                stack.enter_context(mock.patch("shutil.which", return_value="/opt/bin/ollama"))
                mock_run = stack.enter_context(mock.patch("subprocess.run", return_value=cli_ok))
                result = client.generate("Say ✓ hello")

            self.assertEqual(result, "✓ generated response")
            called_cmd = mock_run.call_args.args[0]
            called_kwargs = mock_run.call_args.kwargs
            self.assertEqual(called_cmd[0], "/opt/bin/ollama")
            self.assertEqual(called_kwargs.get("encoding"), "utf-8")
            self.assertEqual(called_kwargs.get("errors"), "replace")
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock


class TestCrossOsJsonRpcAndCli(unittest.TestCase):
    def test_jsonrpc_client_uses_sys_executable_and_utf8_subprocess(self):
        client = JsonRpcClient()
        self.assertEqual(client.python_executable, sys.executable)

        env = client._get_worker_env()
        self.assertEqual(env.get("PYTHONIOENCODING"), "utf-8")
        self.assertEqual(env.get("PYTHONUTF8"), "1")

        fake_proc = mock.MagicMock()
        fake_proc.poll.return_value = None
        fake_proc.stdout.readline.return_value = ""
        with mock.patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            client._ensure_worker()
            called_args = mock_popen.call_args.args[0]
            called_kwargs = mock_popen.call_args.kwargs
            self.assertEqual(called_args, [sys.executable, "-m", "maca.jsonrpc.server"])
            self.assertEqual(called_kwargs.get("encoding"), "utf-8")
            self.assertEqual(called_kwargs.get("errors"), "replace")
            client.close()

    def test_jsonrpc_unicode_roundtrip(self):
        old_mock = os.environ.get("MOCK_GEMMA_FALLBACK")
        os.environ["MOCK_GEMMA_FALLBACK"] = "true"
        try:
            with JsonRpcClient() as client:
                res = client.call(
                    "task_classifier.classify",
                    {"task_description": "Create ✓ café λ helper in app.py"},
                )
                self.assertTrue(res.get("completed"))
                self.assertIn(res.get("result"), ("SIMPLE", "MEDIUM", "COMPLEX", "VERY_COMPLEX"))
        finally:
            if old_mock is not None:
                os.environ["MOCK_GEMMA_FALLBACK"] = old_mock
            else:
                os.environ.pop("MOCK_GEMMA_FALLBACK", None)

    def test_apply_target_input_handles_windows_relative_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(repo_path=tmpdir)
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                new_orch, desc = _apply_target_input(orch, "Build app", ".\\my_sub_app")
                self.assertEqual(desc, "Build app")
                self.assertTrue(os.path.isdir(new_orch.repo_path))
                self.assertEqual(os.path.basename(new_orch.repo_path), "my_sub_app")
            finally:
                os.chdir(old_cwd)

    def test_parse_interactive_command_windows_and_posix(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("task", nargs="?", default=None)
        parser.add_argument("--repo", default=".")
        parser.add_argument("--model", default=None)
        parser.add_argument("--mock", action="store_true")

        task, model, is_cmd = parse_interactive_command(
            'python3 -m maca.main --model gemma "Create app.py"', parser
        )
        self.assertTrue(is_cmd)
        self.assertEqual(task, "Create app.py")
        self.assertEqual(model, "gemma")

        with mock.patch("maca.main.os.name", "nt"):
            win_task, win_model, win_is_cmd = parse_interactive_command(
                'py -3 src\\maca\\main.py --model gemini "Fix path\\to\\file.py"', parser
            )
            self.assertTrue(win_is_cmd)
            self.assertEqual(win_task, "Fix path\\to\\file.py")
            self.assertEqual(win_model, "gemini")

            exe_task, _, exe_is_cmd = parse_interactive_command(
                '.\\maca.exe "Build widget.py"', parser
            )
            self.assertTrue(exe_is_cmd)
            self.assertEqual(exe_task, "Build widget.py")


if __name__ == "__main__":
    unittest.main()
