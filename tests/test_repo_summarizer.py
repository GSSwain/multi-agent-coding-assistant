import tempfile
import unittest
from unittest import mock

from maca.agents.planner import PlannerAgent
from maca.context import TaskContext
from maca.jsonrpc.dispatcher import JsonRpcDispatcher
from maca.orchestrator import Orchestrator
from maca.repo_summarizer import (
    build_repo_map,
    classify_target_vs_reference_files,
    summarize_file_source,
    summarize_python_source,
)
from maca.stages.coding import CodingStage
from maca.stages.planning import PlanningStage


class TestPythonSummarizer(unittest.TestCase):
    def test_summarize_python_skeleton(self):
        source = '''"""Module summary line.

Extended module details that should be omitted.
"""

import os
from typing import Dict, List

MAX_RETRIES = 3
DEFAULT_TIMEOUT: int = 30
internal_var = "ignored"


class AuthService(BaseService):
    """Handles user authentication.

    More details here.
    """

    role_cache: Dict[str, str] = {}

    @classmethod
    def from_env(cls, prefix: str = "AUTH") -> "AuthService":
        """Build from environment variables."""
        secret = os.environ.get(prefix, "hidden_body_token")
        return cls()

    async def verify(self, token: str) -> bool:
        secret_check = token == "super_secret_implementation"
        return secret_check


def helper(items: List[str]) -> int:
    """Count items quickly.

    Second docstring line omitted.
    """
    hidden_local = len(items)
    return hidden_local
'''
        summary = summarize_python_source(source)
        self.assertIn('"""Module summary line."""', summary)
        self.assertNotIn("Extended module details", summary)
        self.assertIn("import os", summary)
        self.assertIn("from typing import Dict, List", summary)
        self.assertIn("MAX_RETRIES = 3", summary)
        self.assertIn("DEFAULT_TIMEOUT: int = 30", summary)
        self.assertNotIn("internal_var", summary)
        self.assertIn("class AuthService(BaseService):", summary)
        self.assertIn('"""Handles user authentication."""', summary)
        self.assertIn("role_cache: Dict[str, str] = {}", summary)
        self.assertIn("@classmethod", summary)
        self.assertIn("def from_env(cls, prefix: str", summary)
        self.assertIn("'AUTH'", summary)
        self.assertIn("-> 'AuthService':", summary)
        self.assertIn("async def verify(self, token: str) -> bool: ...", summary)
        self.assertIn("def helper(items: List[str]) -> int:", summary)
        self.assertIn('"""Count items quickly."""', summary)
        self.assertIn("...", summary)
        self.assertNotIn("hidden_body_token", summary)
        self.assertNotIn("super_secret_implementation", summary)
        self.assertNotIn("hidden_local", summary)
        self.assertNotIn("Second docstring line omitted", summary)

    def test_summarize_python_syntax_error_fallback(self):
        broken_source = "def broken_func(x: int\n    return x + 1\n"
        summary = summarize_python_source(broken_source)
        self.assertIn("def broken_func(x: int", summary)
        self.assertIn("return x + 1", summary)

    def test_summarize_python_empty_source(self):
        self.assertEqual(summarize_python_source(""), "")
        self.assertEqual(summarize_python_source("   \n\t  "), "")


class TestMultiLanguageSummarizer(unittest.TestCase):
    def test_summarize_typescript_source(self):
        ts_source = """import { Request, Response } from "express";

export interface User {
  id: string;
  name: string;
}

export class UserController {
  public async getUser(req: Request, res: Response): Promise<void> {
    if (req.params.id) {
      res.json({ secretBody: true });
    }
  }
}

export const formatUser = (user: User): string => {
  return user.name.toUpperCase();
};
"""
        summary = summarize_file_source("src/controller.ts", ts_source)
        self.assertIn('import { Request, Response } from "express";', summary)
        self.assertIn("export interface User", summary)
        self.assertIn("export class UserController", summary)
        self.assertIn("public async getUser(req: Request, res: Response): Promise<void>", summary)
        self.assertIn("export const formatUser = (user: User): string =>", summary)
        self.assertNotIn("secretBody", summary)
        self.assertNotIn("if (req.params.id)", summary)

    def test_summarize_javascript_source(self):
        js_source = """import express from "express";

export function createServer(port) {
  const secretValue = 42;
  return express().listen(port);
}
"""
        summary = summarize_file_source("server.js", js_source)
        self.assertIn('import express from "express";', summary)
        self.assertIn("export function createServer(port)", summary)
        self.assertNotIn("secretValue", summary)

    def test_summarize_java_source(self):
        java_source = """package com.example.auth;

import java.util.Optional;

public class AuthController {
    private final String secret = new String("hidden");

    public Optional<String> login(String user, String pass) {
        String bodyDetail = user + pass;
        return Optional.of(bodyDetail);
    }
}
"""
        summary = summarize_file_source("src/AuthController.java", java_source)
        self.assertIn("package com.example.auth;", summary)
        self.assertIn("import java.util.Optional;", summary)
        self.assertIn("public class AuthController", summary)
        self.assertIn("public Optional<String> login(String user, String pass)", summary)
        self.assertNotIn("bodyDetail", summary)
        self.assertNotIn("new String", summary)

    def test_summarize_go_source(self):
        go_source = """package server

import (
    "context"
    "net/http"
)

type Handler struct {
    addr string
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    secretBody := "hidden"
    _, _ = w.Write([]byte(secretBody))
}

func Start(ctx context.Context) error {
    return nil
}
"""
        summary = summarize_file_source("pkg/server.go", go_source)
        self.assertIn("package server", summary)
        self.assertIn('"context"', summary)
        self.assertIn('"net/http"', summary)
        self.assertIn("type Handler struct", summary)
        self.assertIn(
            "func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request)",
            summary,
        )
        self.assertIn("func Start(ctx context.Context) error", summary)
        self.assertNotIn("secretBody", summary)

    def test_summarize_rust_source(self):
        rs_source = """use std::io::Result;

pub struct Engine {
    threads: usize,
}

impl Engine {
    pub async fn run(&self) -> Result<()> {
        let hidden_body = self.threads;
        Ok(())
    }
}
"""
        summary = summarize_file_source("src/engine.rs", rs_source)
        self.assertIn("use std::io::Result;", summary)
        self.assertIn("pub struct Engine", summary)
        self.assertIn("impl Engine", summary)
        self.assertIn("pub async fn run(&self) -> Result<()>", summary)
        self.assertNotIn("hidden_body", summary)

    def test_summarize_plain_text_fallback_and_max_lines(self):
        text = "\n".join(f"line {i}" for i in range(1, 21))
        summary = summarize_file_source("notes.txt", text, max_lines=5)
        lines = summary.splitlines()
        self.assertLessEqual(len(lines), 5)
        self.assertIn("line 1", lines[0])
        self.assertIn("more lines omitted", lines[-1])


class TestBuildRepoMap(unittest.TestCase):
    def test_build_repo_map_caps_files_and_chars(self):
        files = {
            "a.py": "def alpha(x: int) -> int:\n    return x + 1\n",
            "b.py": "def beta(y: str) -> str:\n    return y.strip()\n",
            "c.py": "def gamma() -> None:\n    pass\n",
            "logo.png": "binary-data",
            ".maca/task/plan.md": "# internal plan",
        }
        repo_map = build_repo_map(
            list(files.keys()),
            read_fn=lambda fp: files[fp],
            max_files=2,
            max_chars=8000,
        )
        self.assertIn("### a.py", repo_map)
        self.assertIn("### b.py", repo_map)
        self.assertNotIn("### c.py", repo_map)
        self.assertNotIn("logo.png", repo_map)
        self.assertNotIn(".maca/task/plan.md", repo_map)
        self.assertIn("truncated", repo_map)

    def test_build_repo_map_strict_max_chars(self):
        files = {
            "mod1.py": "\n".join(f"def fn_{i}(x: int) -> int:\n    return x" for i in range(20)),
            "mod2.py": "\n".join(f"def g_{i}(y: str) -> str:\n    return y" for i in range(20)),
        }
        repo_map = build_repo_map(
            list(files.keys()),
            read_fn=lambda fp: files[fp],
            max_files=10,
            max_chars=180,
        )
        self.assertLessEqual(len(repo_map), 180)
        self.assertIn("### mod1.py", repo_map)

    def test_build_repo_map_skips_maca_and_binary_files(self):
        files = {
            ".maca/task/plan.md": "# internal plan",
            "./.maca/task/spec.md": "# internal spec",
            "sub/.maca/meta.json": '{"status": "ok"}',
            "logo.png": "binary-data",
            "a.py": "def alpha(x: int) -> int:\n    return x + 1\n",
        }
        repo_map = build_repo_map(
            list(files.keys()),
            read_fn=lambda fp: files[fp],
            max_files=10,
            max_chars=8000,
        )
        self.assertIn("### a.py", repo_map)
        self.assertNotIn("plan.md", repo_map)
        self.assertNotIn("spec.md", repo_map)
        self.assertNotIn("meta.json", repo_map)
        self.assertNotIn("logo.png", repo_map)

    def test_build_repo_map_skips_read_errors(self):
        def read_fn(fp: str) -> str:
            if fp == "bad.py":
                return "Error: outside allowed directory"
            return "def ok() -> bool:\n    return True\n"

        repo_map = build_repo_map(["bad.py", "good.py"], read_fn=read_fn)
        self.assertNotIn("bad.py", repo_map)
        self.assertIn("### good.py", repo_map)


class TestClassifyTargetVsReference(unittest.TestCase):
    def test_explicit_modify_vs_reference_tags(self):
        plan = "- [MODIFY] src/auth.py: add JWT support\n- [REF] src/models.py: User fields\n"
        targets, refs = classify_target_vs_reference_files(
            ["src/auth.py", "src/models.py", "src/unused.py"],
            plan=plan,
            spec="",
        )
        self.assertEqual(targets, ["src/auth.py"])
        self.assertEqual(refs, ["src/models.py"])

    def test_explicit_modify_tags_classify_untagged_context_as_reference(self):
        plan = "- [MODIFY] src/auth.py\n- src/schema.py defines the token payload.\n"
        targets, refs = classify_target_vs_reference_files(
            ["src/auth.py", "src/schema.py"],
            plan=plan,
            spec="",
        )
        self.assertEqual(targets, ["src/auth.py"])
        self.assertEqual(refs, ["src/schema.py"])

    def test_ambiguous_mentions_default_to_target(self):
        targets, refs = classify_target_vs_reference_files(
            ["auth.py", "db.py", "other.py"],
            plan="1. Update auth.py",
            spec="Spec details db.py connection",
        )
        self.assertEqual(targets, ["auth.py", "db.py"])
        self.assertEqual(refs, [])

    def test_reference_phrasing_without_tags(self):
        targets, refs = classify_target_vs_reference_files(
            ["main.py", "utils.py"],
            plan="1. Update main.py",
            spec="See utils.py for helper signatures",
        )
        self.assertEqual(targets, ["main.py"])
        self.assertEqual(refs, ["utils.py"])


class TestPlannerAndCodingIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orch = Orchestrator(repo_path=self.temp_dir.name, allowed_directory=".")
        self.ctx = TaskContext(
            task="Add login endpoint",
            task_name="add-login",
            repo_path=self.temp_dir.name,
            allowed_directory=".",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_planner_prompt_omits_repo_map_when_empty(self):
        planner = PlannerAgent(mock.MagicMock())
        prompt = planner._build_prompt("Add login", ["app.py"], [])
        self.assertNotIn("## Repository Structure Summary", prompt)

    def test_planner_prompt_injects_repo_map(self):
        mock_client = mock.MagicMock()
        mock_client.generate.return_value = "1. [MODIFY] app.py"
        planner = PlannerAgent(mock_client)
        repo_map = "### app.py\ndef login(user: str) -> bool: ..."
        planner.run("Add login", ["app.py"], repo_map=repo_map)

        called_prompt = mock_client.generate.call_args[0][0]
        self.assertIn("## Repository Structure Summary", called_prompt)
        self.assertIn("def login(user: str) -> bool: ...", called_prompt)

    def test_planning_stage_passes_repo_map_in_ipc_payload(self):
        self.orch.workspace.write_file(
            "service.py",
            "def authenticate(user: str) -> bool:\n    secret_body = True\n    return secret_body\n",
        )
        stage = PlanningStage(self.orch)
        with mock.patch.object(
            self.orch, "call_agent", return_value={"result": "- [MODIFY] service.py"}
        ) as mock_call:
            plan, repo_files = stage.plan_task(
                task_description="Add MFA",
                task_context=self.ctx,
                client=None,
                model_name="GEMMA",
            )
            self.assertEqual(plan, "- [MODIFY] service.py")
            self.assertIn("service.py", repo_files)
            sent_payload = mock_call.call_args[0][1]
            self.assertIn("repo_map", sent_payload)
            self.assertIn("### service.py", sent_payload["repo_map"])
            self.assertIn("def authenticate(user: str) -> bool: ...", sent_payload["repo_map"])
            self.assertNotIn("secret_body", sent_payload["repo_map"])

    def test_jsonrpc_dispatcher_forwards_repo_map_to_planner(self):
        dispatcher = JsonRpcDispatcher()
        fake_client = mock.MagicMock()
        fake_client.generate.return_value = "- [MODIFY] app.py"
        with mock.patch("maca.jsonrpc.dispatcher.get_model_client", return_value=fake_client):
            res = dispatcher.dispatch(
                "maca.agents.planner",
                {
                    "task_description": "Add health check",
                    "repo_files": ["app.py"],
                    "repo_map": "### app.py\ndef start() -> None: ...",
                    "repo_path": self.temp_dir.name,
                },
            )
        self.assertEqual(res["result"], "- [MODIFY] app.py")
        called_prompt = fake_client.generate.call_args[0][0]
        self.assertIn("## Repository Structure Summary", called_prompt)
        self.assertIn("def start() -> None: ...", called_prompt)

    def test_coding_stage_collect_repo_files_default_vs_summarized_references(self):
        self.orch.workspace.write_file(
            "auth.py",
            "def login(user: str) -> bool:\n    auth_body = True\n    return auth_body\n",
        )
        models_src = (
            "class User:\n"
            "    def check(self) -> bool:\n"
            "        model_body = True\n"
            "        return model_body\n"
        )
        self.orch.workspace.write_file("models.py", models_src)
        self.orch.workspace.write_file("unused.py", "def noop() -> None:\n    pass\n")

        stage = CodingStage(self.orch)
        plan = "- [MODIFY] auth.py: update login\n- [REF] models.py: User definition"
        spec = ""

        # Default behavior preserves full content for all mentioned files
        full_content = stage.collect_repo_files_content(
            ["auth.py", "models.py", "unused.py"], plan=plan, spec=spec
        )
        self.assertIn("auth_body", full_content["auth.py"])
        self.assertIn("model_body", full_content["models.py"])
        self.assertNotIn("unused.py", full_content)

        # With summarize_references=True, target stays full while reference is summarized
        summarized = stage.collect_repo_files_content(
            ["auth.py", "models.py", "unused.py"],
            plan=plan,
            spec=spec,
            summarize_references=True,
        )
        self.assertIn("auth_body", summarized["auth.py"])
        self.assertIn("[Read-only reference summary]", summarized["models.py"])
        self.assertIn("class User:", summarized["models.py"])
        self.assertIn("def check(self) -> bool: ...", summarized["models.py"])
        self.assertNotIn("model_body", summarized["models.py"])
        self.assertNotIn("unused.py", summarized)


if __name__ == "__main__":
    unittest.main()
