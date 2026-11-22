import json
import re
from typing import Any, Callable, Dict, List, Optional

from maca.agents.base import BaseAgent
from maca.clarifier import FrameworkBootstrapClarifier
from maca.todo import write_todo_file


class ClarifierAgent(BaseAgent):
    """Architecture Clarifier Agent.

    Uses an LLM to analyze user tasks for greenfield framework bootstrapping,
    identifies the target stack, extracts pre-specified parameters, and
    dynamically formulates clarifying questions for ambiguous architectural choices.
    """

    def __init__(
        self,
        model_client: Any,
        repo_path: str = ".",
        allowed_directory: Optional[str] = None,
    ):
        super().__init__(
            "Clarifier",
            model_client,
            repo_path=repo_path,
            allowed_directory=allowed_directory,
        )

    def _build_system_instruction(self, *args: Any, **kwargs: Any) -> str:
        return (
            "You are an expert Software Architecture Clarifier Agent in a multi-agent coding system.\n"
            "Your job is to analyze the user's task to determine if it involves bootstrapping, "
            "scaffolding, or initializing a new project or application framework "
            "(e.g., Spring Boot, Spring Framework, Next.js, React, FastAPI, Django, Express, "
            "NestJS, Go Gin, Rust Axum/Actix, etc.).\n\n"
            "INSTRUCTIONS:\n"
            "1. If the task is NOT bootstrapping a new framework/project (e.g. bug fixes, simple scripts, "
            "utility functions, algorithms, documentation, modifying existing code), return:\n"
            '   {"is_bootstrap": false, "framework": null, "questions": []}\n\n'
            "2. If the task DOES involve bootstrapping a framework/project:\n"
            "   a. Identify the framework name (e.g. 'Spring Boot', 'Next.js', 'React', 'FastAPI').\n"
            "   b. Extract any parameters ALREADY specified in the user's prompt into 'resolved_params' "
            "(e.g. build tool, language, runtime version).\n"
            "   c. For remaining ambiguous, decisive architectural choices (1 to 4 questions), "
            "formulate clear multiple-choice questions. Mark the modern LTS industry standard "
            "choice with '(Recommended)'.\n"
            "   d. Provide a modern recommended default value for each question.\n"
            "   e. Use lowercase snake_case for all keys (e.g., 'build_tool', 'java_version', 'language', 'package_manager', 'router').\n\n"
            "RESPONSE FORMAT:\n"
            "You MUST respond ONLY with a valid JSON object matching this schema:\n"
            "{\n"
            '  "is_bootstrap": true,\n'
            '  "framework": "Framework Name",\n'
            '  "resolved_params": {\n'
            '    "param_name": "value"\n'
            "  },\n"
            '  "questions": [\n'
            "    {\n"
            '      "key": "param_name",\n'
            '      "question": "Question text",\n'
            '      "choices": ["Option 1 (Recommended)", "Option 2"],\n'
            '      "default": "Option 1"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Do NOT include conversational markdown prose outside the JSON."
        )

    def _build_prompt(self, task_description: str, *args: Any, **kwargs: Any) -> str:
        return (
            f"User Task: {task_description}\n\n"
            "Analyze whether this task requires framework bootstrapping. If so, identify the "
            "framework, extract pre-specified parameters, and formulate necessary architectural "
            "clarification questions. Output strictly valid JSON."
        )

    def _parse_llm_json(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON object from LLM response text."""
        cleaned = response_text.strip()
        # Handle markdown code blocks
        if "```" in cleaned:
            matches = re.findall(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
            if matches:
                cleaned = matches[0].strip()

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "is_bootstrap" in data:
                return data
        except Exception:
            pass

        # Try regex search for outermost { ... }
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict) and "is_bootstrap" in data:
                    return data
            except Exception:
                pass

        return None

    @staticmethod
    def _normalize_key(key: str, framework: Optional[str] = None) -> str:
        """Convert camelCase/PascalCase/spaced keys to lowercase snake_case and map aliases."""
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
        s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
        s3 = re.sub(r"[\s\-]+", "_", s2)
        norm = s3.lower().strip("_")

        aliases = {
            "build_system": "build_tool",
            "build_utility": "build_tool",
            "java": "java_version",
            "jdk": "java_version",
            "jdk_version": "java_version",
            "boot_version": "spring_boot_version",
            "spring_version": "spring_boot_version",
        }
        mapped = aliases.get(norm, norm)
        if framework and "spring" in framework.lower() and mapped == "runtime_version":
            mapped = "java_version"
        return mapped

    @staticmethod
    def _clean_choice_value(val: str) -> str:
        """Strip numbering prefixes (e.g. '1: ') and '(Recommended)' tags."""
        cleaned = re.sub(r"\s*\(Recommended\)\s*", "", val, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^\d+[:\.)]\s*", "", cleaned).strip()
        return cleaned

    def clarify(
        self,
        task_description: str,
        prompt_ask_fn: Optional[Callable[..., str]] = None,
        interactive: bool = True,
        task_name: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """Clarify architectural choices using LLM with deterministic fallback."""
        llm_data: Optional[Dict[str, Any]] = None

        # 1. Attempt LLM generation
        try:
            raw_response = self.run(task_description)
            llm_data = self._parse_llm_json(raw_response)
        except Exception:
            llm_data = None

        # 2. If LLM provided valid structured output
        if llm_data is not None:
            if not llm_data.get("is_bootstrap"):
                return None

            framework = str(llm_data.get("framework") or "Unknown Framework")
            resolved_params: Dict[str, str] = {
                self._normalize_key(str(k), framework): str(v)
                for k, v in llm_data.get("resolved_params", {}).items()
            }
            questions: List[Dict[str, Any]] = llm_data.get("questions", [])

            bootstrap_config: Dict[str, str] = {"framework": framework}
            bootstrap_config.update(resolved_params)

            for q in questions:
                raw_key = str(q.get("key", ""))
                key = self._normalize_key(raw_key, framework)
                if not key or key in bootstrap_config:
                    continue

                q_text = str(q.get("question", key.replace("_", " ").title()))
                raw_choices = [str(c) for c in q.get("choices", [])]
                default_val = str(q.get("default", raw_choices[0] if raw_choices else ""))
                clean_default = self._clean_choice_value(default_val)

                if interactive and prompt_ask_fn and raw_choices:
                    formatted_choices = [
                        f"{i + 1}: {self._clean_choice_value(c)}" for i, c in enumerate(raw_choices)
                    ]
                    prompt_label = (
                        f"\n[bold cyan]{q_text}[/bold cyan] ({', '.join(formatted_choices)})"
                    )
                    valid_choices = [str(i + 1) for i in range(len(raw_choices))] + raw_choices

                    try:
                        ans = prompt_ask_fn(
                            prompt_label,
                            choices=valid_choices,
                            default=raw_choices[0],
                        )
                        ans_str = str(ans or "").strip()
                        if ans_str in [str(i + 1) for i in range(len(raw_choices))]:
                            chosen = raw_choices[int(ans_str) - 1]
                        elif ans_str:
                            chosen = ans_str
                        else:
                            chosen = default_val

                        bootstrap_config[key] = self._clean_choice_value(chosen)
                    except Exception:
                        bootstrap_config[key] = clean_default
                else:
                    bootstrap_config[key] = clean_default

            if task_name:
                self._record_todo(task_name, framework, bootstrap_config)

            return bootstrap_config

        # 3. Fallback: Use deterministic FrameworkBootstrapClarifier
        fallback_config = FrameworkBootstrapClarifier.clarify(
            task_description=task_description,
            prompt_ask_fn=prompt_ask_fn,
            interactive=interactive,
        )
        if fallback_config and task_name:
            self._record_todo(
                task_name,
                fallback_config.get("framework", "Framework"),
                fallback_config,
            )
        return fallback_config

    def _record_todo(self, task_name: str, framework: str, config_dict: Dict[str, str]) -> None:
        items = "\n".join(f"- [x] {k}: {v}" for k, v in config_dict.items())
        todo_text = (
            f"# Todo Progress for task: {task_name} (clarifier)\n"
            f"- [x] Analyzed task for framework bootstrapping\n"
            f"- [x] Configured {framework} architectural choices:\n"
            f"{items}\n"
        )
        write_todo_file(self.repo_path, task_name, "clarifier", todo_text)


if __name__ == "__main__":
    import sys

    from maca.models.factory import get_model_client

    payload = json.loads(sys.stdin.read())
    args = payload.get("args", {})
    context = args.get("context", {})
    client = get_model_client(args.get("model_name"))
    repo_path = args.get("repo_path") or context.get("repo_path", ".")
    task_name = args.get("task_name") or context.get("task_name", "")
    task_desc = args.get("task_description") or context.get("task", "")
    allowed_dir = args.get("allowed_directory") or context.get("allowed_directory") or "."
    interactive = args.get("interactive", False)

    agent = ClarifierAgent(client, repo_path=repo_path, allowed_directory=allowed_dir)
    result = agent.clarify(
        task_description=task_desc,
        prompt_ask_fn=None,
        interactive=interactive,
        task_name=task_name,
    )
    json.dump(
        {
            "result": result,
            "agent": "clarifier",
            "completed": True,
            "update": {"bootstrap_config": result},
        },
        sys.stdout,
    )
