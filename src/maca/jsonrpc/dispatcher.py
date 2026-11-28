import os
from typing import Any, Callable, Dict, List, Optional

from maca.agents.clarifier import ClarifierAgent
from maca.agents.code_completion_verifier import CodeCompletionVerifierAgent
from maca.agents.coder import BaseCoderAgent, SimpleCoderAgent, SpecCoderAgent
from maca.agents.planner import PlannerAgent
from maca.agents.reviewer import ReviewerAgent
from maca.agents.spec import SpecAgent
from maca.agents.task_classifier import TaskClassifierAgent
from maca.jsonrpc.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    JsonRpcError,
)
from maca.models.factory import get_model_client


class JsonRpcDispatcher:
    """Dispatches JSON-RPC 2.0 requests to the appropriate agent handler."""

    def __init__(
        self,
        notify_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self.notify_callback = notify_callback
        self._register_default_handlers()

    def emit_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Emit an asynchronous JSON-RPC 2.0 notification if a callback is configured."""
        if self.notify_callback is not None:
            self.notify_callback(method, params)

    def register(self, method: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a handler for a method name."""
        self._handlers[method] = handler

    def list_methods(self) -> List[str]:
        """Return a sorted list of registered method names."""
        return sorted(self._handlers.keys())

    def dispatch(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Dispatch a method invocation with the given parameter dictionary."""
        effective_params = dict(params) if params else {}
        if "_env" in effective_params:
            env_overrides = effective_params.pop("_env")
            if isinstance(env_overrides, dict):
                for k, v in env_overrides.items():
                    if v is not None:
                        os.environ[k] = str(v)
                    else:
                        os.environ.pop(k, None)
                from maca import maca_config as config

                config.MOCK_GEMMA_FALLBACK = (
                    os.environ.get("MOCK_GEMMA_FALLBACK", "").lower() == "true"
                )

        handler = self._handlers.get(method)
        if not handler:
            raise JsonRpcError(
                METHOD_NOT_FOUND,
                f"Method not found: '{method}'",
                data={"available_methods": self.list_methods()},
            )
        try:
            return handler(effective_params)
        except JsonRpcError:
            raise
        except TypeError as e:
            raise JsonRpcError(INVALID_PARAMS, f"Invalid params for method '{method}': {e}") from e
        except Exception as e:
            raise JsonRpcError(INTERNAL_ERROR, f"Internal error executing '{method}': {e}") from e

    # -------------------------------------------------------------------------
    # Default Agent Handlers
    # -------------------------------------------------------------------------

    def _register_default_handlers(self) -> None:
        # System
        self.register("system.ping", lambda _: "pong")
        self.register("system.methods", lambda _: self.list_methods())

        # Task Classifier
        self.register("task_classifier.classify", self._handle_task_classifier)
        self.register("maca.agents.task_classifier", self._handle_task_classifier)

        # Clarifier
        self.register("clarifier.clarify", self._handle_clarifier)
        self.register("maca.agents.clarifier", self._handle_clarifier)

        # Planner
        self.register("planner.plan", self._handle_planner)
        self.register("maca.agents.planner", self._handle_planner)

        # Spec
        self.register("spec.spec", self._handle_spec)
        self.register("maca.agents.spec", self._handle_spec)

        # Coder
        self.register("coder.generate", self._handle_coder)
        self.register("maca.agents.coder", self._handle_coder)

        # Code Completion Verifier
        self.register("code_completion_verifier.verify", self._handle_verifier)
        self.register("maca.agents.code_completion_verifier", self._handle_verifier)

        # Reviewer
        self.register("reviewer.review", self._handle_reviewer)
        self.register("maca.agents.reviewer", self._handle_reviewer)

    def _handle_task_classifier(self, params: Dict[str, Any]) -> Dict[str, Any]:
        context = params.get("context", {})
        task_desc = params.get("task_description") or context.get("task", "")
        agent = TaskClassifierAgent()
        complexity = agent.classify(task_desc)
        return {
            "result": complexity,
            "agent": "task_classifier",
            "completed": True,
            "update": {"complexity": complexity},
        }

    def _handle_clarifier(self, params: Dict[str, Any]) -> Dict[str, Any]:
        context = params.get("context", {})
        task_desc = params.get("task_description") or context.get("task", "")
        task_name = params.get("task_name") or context.get("task_name", "")
        repo_path = params.get("repo_path") or context.get("repo_path", ".")
        allowed_dir = params.get("allowed_directory") or context.get("allowed_directory") or "."
        interactive = params.get("interactive", False)
        model_name = params.get("model_name")
        client = get_model_client(model_name)
        agent = ClarifierAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
        res = agent.clarify(
            task_description=task_desc,
            prompt_ask_fn=None,
            interactive=interactive,
            task_name=task_name,
        )
        return {
            "result": res,
            "agent": "clarifier",
            "completed": True,
            "update": {"bootstrap_config": res},
        }

    def _handle_planner(self, params: Dict[str, Any]) -> Dict[str, Any]:
        context = params.get("context", {})
        client = get_model_client(params.get("model_name"))
        repo_path = params.get("repo_path") or context.get("repo_path", ".")
        task_name = params.get("task_name") or context.get("task_name", "")
        task_desc = params.get("task_description") or context.get("task", "")
        allowed_dir = params.get("allowed_directory") or context.get("allowed_directory") or "."

        agent = PlannerAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
        repo_files = (
            params["repo_files"]
            if "repo_files" in params and params["repo_files"] is not None
            else agent.list_files()
        )
        repo_map = str(params.get("repo_map") or context.get("repo_map", "") or "")
        result = agent.run(
            task_description=task_desc,
            repo_files=repo_files,
            history=params.get("history"),
            task_name=task_name,
            repo_map=repo_map,
        )
        return {
            "result": result,
            "agent": "planner",
            "completed": True,
            "update": {"plan": result, "allowed_directory": allowed_dir},
        }

    def _handle_spec(self, params: Dict[str, Any]) -> Dict[str, Any]:
        context = params.get("context", {})
        client = get_model_client(params.get("model_name"))
        repo_path = params.get("repo_path") or context.get("repo_path", ".")
        task_name = params.get("task_name") or context.get("task_name", "")
        task_desc = params.get("task_description") or context.get("task", "")
        plan = params.get("plan") or context.get("plan", "")
        allowed_dir = params.get("allowed_directory") or context.get("allowed_directory") or "."

        agent = SpecAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
        result = agent.run(
            task_description=task_desc,
            plan=plan,
            history=params.get("history"),
            task_name=task_name,
        )
        return {
            "result": result,
            "agent": "spec",
            "completed": True,
            "update": {"spec": result, "allowed_directory": allowed_dir},
        }

    def _handle_coder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        context = params.get("context", {})
        client = get_model_client(params.get("model_name"))
        repo_path = params.get("repo_path") or context.get("repo_path", ".")
        coder_type = params.get("coder_type", "SIMPLE")
        task_name = params.get("task_name") or context.get("task_name", "")
        task_desc = params.get("task_description") or context.get("task", "")
        plan = params.get("plan") or context.get("plan", "")
        spec = params.get("spec") or context.get("spec", "")
        allowed_dir = params.get("allowed_directory") or context.get("allowed_directory") or "."
        nudge = params.get("nudge", "")

        coder: BaseCoderAgent
        if coder_type == "SIMPLE":
            coder = SimpleCoderAgent(
                "SimpleCoder", client, repo_path=repo_path, allowed_directory=allowed_dir
            )
            result = coder.run(
                task_description=task_desc,
                plan=plan,
                repo_files_content=params.get("repo_files_content"),
                history=params.get("history"),
                task_name=task_name,
                nudge=nudge,
                allowed_directory=allowed_dir,
            )
        else:
            coder = SpecCoderAgent(
                "SpecCoder", client, repo_path=repo_path, allowed_directory=allowed_dir
            )
            result = coder.run(
                task_description=task_desc,
                spec=spec,
                repo_files_content=params.get("repo_files_content"),
                history=params.get("history"),
                task_name=task_name,
                nudge=nudge,
                allowed_directory=allowed_dir,
            )

        parsed_files = coder.parse_files(result)
        file_blocks = coder.compute_file_blocks(parsed_files, params.get("repo_files_content"))
        for fp, content in parsed_files.items():
            self.emit_notification(
                "progress.stream",
                {
                    "agent": "coder",
                    "file": fp,
                    "size": len(content),
                    "chunk_preview": content[:120],
                },
            )
        return {
            "result": result,
            "files": parsed_files,
            "file_blocks": file_blocks,
            "agent": "coder",
            "completed": True,
            "update": {
                "files": parsed_files,
                "file_blocks": file_blocks,
                "allowed_directory": allowed_dir,
            },
        }

    def _handle_verifier(self, params: Dict[str, Any]) -> Dict[str, Any]:
        context = params.get("context", {})
        client = get_model_client(params.get("model_name"))
        repo_path = params.get("repo_path") or context.get("repo_path", ".")
        task_name = params.get("task_name") or context.get("task_name", "")
        task_desc = params.get("task_description") or context.get("task", "")
        spec = params.get("spec") or context.get("spec") or context.get("plan", "")
        allowed_dir = params.get("allowed_directory") or context.get("allowed_directory") or "."

        agent = CodeCompletionVerifierAgent(
            client, repo_path=repo_path, allowed_directory=allowed_dir
        )
        is_done, feedback = agent.validate(
            task_description=task_desc,
            spec=spec,
            generated_files=params.get("generated_files", {}),
            task_name=task_name,
        )
        return {
            "result": feedback,
            "is_done": is_done,
            "feedback": feedback,
            "agent": "code_completion_verifier",
            "completed": is_done,
            "update": {
                "is_done": is_done,
                "feedback": feedback,
                "allowed_directory": allowed_dir,
            },
        }

    def _handle_reviewer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        context = params.get("context", {})
        client = get_model_client(params.get("model_name"))
        repo_path = params.get("repo_path") or context.get("repo_path", ".")
        task_name = params.get("task_name") or context.get("task_name", "")
        task_desc = params.get("task_description") or context.get("task", "")
        plan_or_spec = params.get("plan_or_spec") or context.get("spec") or context.get("plan", "")
        allowed_dir = params.get("allowed_directory") or context.get("allowed_directory") or "."

        agent = ReviewerAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
        result = agent.run(
            task_description=task_desc,
            generated_files=params.get("generated_files", {}),
            history=params.get("history"),
            plan_or_spec=plan_or_spec,
            file_blocks=params.get("file_blocks"),
            task_name=task_name,
        )
        is_approved = agent.is_approved(result)
        parsed_files = agent.parse_files(result)
        return {
            "result": result,
            "approved": is_approved,
            "files": parsed_files,
            "agent": "reviewer",
            "completed": is_approved,
            "update": {
                "approved": is_approved,
                "files_count": len(parsed_files),
                "files": list(parsed_files.keys()),
                "allowed_directory": allowed_dir,
            },
        }
