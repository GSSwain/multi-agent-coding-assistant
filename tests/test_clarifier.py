import unittest
from unittest.mock import MagicMock

from maca.agents.clarifier import ClarifierAgent
from maca.clarifier import FrameworkBootstrapClarifier


class TestFrameworkBootstrapClarifier(unittest.TestCase):
    def test_detect_framework(self):
        self.assertEqual(
            FrameworkBootstrapClarifier.detect_framework("Creating a hello world spring boot app"),
            "spring_boot",
        )
        self.assertEqual(
            FrameworkBootstrapClarifier.detect_framework(
                "Build a Spring microservice with REST API"
            ),
            "spring_boot",
        )
        self.assertEqual(
            FrameworkBootstrapClarifier.detect_framework("Configure a Spring MVC web application"),
            "spring_framework",
        )
        self.assertEqual(
            FrameworkBootstrapClarifier.detect_framework("Setup a Spring Framework XML project"),
            "spring_framework",
        )
        self.assertEqual(
            FrameworkBootstrapClarifier.detect_framework(
                "Initialize a new Next.js web application"
            ),
            "nextjs",
        )
        self.assertEqual(
            FrameworkBootstrapClarifier.detect_framework("Bootstrap a create-react-app project"),
            "react",
        )
        self.assertEqual(
            FrameworkBootstrapClarifier.detect_framework("Build a modern React app"),
            "react",
        )
        self.assertIsNone(
            FrameworkBootstrapClarifier.detect_framework("Fix a bug in database queries")
        )

    def test_clarify_non_framework_task_returns_none(self):
        result = FrameworkBootstrapClarifier.clarify(
            "Write a simple sorting algorithm in Python", interactive=False
        )
        self.assertIsNone(result)

    def test_clarify_spring_boot_non_interactive_defaults(self):
        result = FrameworkBootstrapClarifier.clarify(
            "Creating a hello world spring boot app", interactive=False
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["framework"], "Spring Boot")
        self.assertEqual(result["build_tool"], "Maven")
        self.assertEqual(result["java_version"], "21")
        self.assertEqual(result["spring_boot_version"], "3.3.x")
        self.assertEqual(result["language"], "Java")

    def test_clarify_spring_boot_respects_explicit_prompt_parameters(self):
        result = FrameworkBootstrapClarifier.clarify(
            "Create a Spring Boot app with Gradle and Java 17 using Kotlin",
            interactive=False,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["build_tool"], "Gradle (Kotlin DSL)")
        self.assertEqual(result["java_version"], "17")
        self.assertEqual(result["language"], "Kotlin")
        self.assertEqual(result["spring_boot_version"], "3.3.x")

    def test_clarify_spring_boot_interactive_user_choices(self):
        # User chooses: Gradle (2), Java 17 (2), Spring Boot 3.2.x (2), Kotlin (2)
        mock_prompt = MagicMock(side_effect=["2", "2", "2", "2"])

        result = FrameworkBootstrapClarifier.clarify(
            "Creating a hello world spring boot app",
            prompt_ask_fn=mock_prompt,
            interactive=True,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["build_tool"], "Gradle (Kotlin DSL)")
        self.assertEqual(result["java_version"], "17")
        self.assertEqual(result["spring_boot_version"], "3.2.x")
        self.assertEqual(result["language"], "Kotlin")
        self.assertEqual(mock_prompt.call_count, 4)

    def test_clarify_spring_boot_interactive_enter_accepts_defaults(self):
        # User presses Enter on all prompts (returns empty string or None)
        mock_prompt = MagicMock(side_effect=["", "", "", ""])

        result = FrameworkBootstrapClarifier.clarify(
            "Creating a hello world spring boot app",
            prompt_ask_fn=mock_prompt,
            interactive=True,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["build_tool"], "Maven")
        self.assertEqual(result["java_version"], "21")
        self.assertEqual(result["spring_boot_version"], "3.3.x")
        self.assertEqual(result["language"], "Java")

    def test_clarify_nextjs_interactive(self):
        # User chooses TypeScript (default) and Pages Router (2)
        mock_prompt = MagicMock(side_effect=["", "2"])

        result = FrameworkBootstrapClarifier.clarify(
            "Create a Next.js portal",
            prompt_ask_fn=mock_prompt,
            interactive=True,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["framework"], "Next.js")
        self.assertEqual(result["language"], "TypeScript")
        self.assertEqual(result["router"], "Pages Router")

    def test_clarify_react_defaults_and_interactive(self):
        # Non-interactive defaults to Vite & TypeScript
        res_default = FrameworkBootstrapClarifier.clarify(
            "Build a React app",
            interactive=False,
        )
        self.assertIsNotNone(res_default)
        assert res_default is not None
        self.assertEqual(res_default["framework"], "React")
        self.assertEqual(res_default["bundler"], "Vite")
        self.assertEqual(res_default["language"], "TypeScript")

        # Explicit create-react-app in prompt
        res_cra = FrameworkBootstrapClarifier.clarify(
            "Bootstrap a create-react-app project with javascript",
            interactive=False,
        )
        self.assertIsNotNone(res_cra)
        assert res_cra is not None
        self.assertEqual(res_cra["bundler"], "Create React App (CRA)")
        self.assertEqual(res_cra["language"], "JavaScript")

    def test_clarify_spring_framework_classic(self):
        # Non-interactive defaults to WAR, Java Config, Maven
        res = FrameworkBootstrapClarifier.clarify(
            "Configure a Spring MVC web application",
            interactive=False,
        )
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res["framework"], "Spring Framework (Classic)")
        self.assertEqual(res["packaging"], "WAR (Servlet Container deployment)")
        self.assertEqual(res["configuration"], "Java Config (@Configuration)")
        self.assertEqual(res["build_tool"], "Maven")

        # Explicit XML configuration and Gradle
        res_xml = FrameworkBootstrapClarifier.clarify(
            "Configure a Spring Framework project with XML and Gradle",
            interactive=False,
        )
        self.assertIsNotNone(res_xml)
        assert res_xml is not None
        self.assertEqual(res_xml["configuration"], "XML (applicationContext.xml)")
        self.assertEqual(res_xml["build_tool"], "Gradle")


class TestClarifierAgent(unittest.TestCase):
    def test_clarifier_agent_non_bootstrap(self):
        mock_client = MagicMock()
        mock_client.generate.return_value = (
            '{"is_bootstrap": false, "framework": null, "questions": []}'
        )
        agent = ClarifierAgent(mock_client)
        result = agent.clarify("Fix a typo in documentation", interactive=False)
        self.assertIsNone(result)

    def test_clarifier_agent_dynamic_framework(self):
        mock_client = MagicMock()
        mock_client.generate.return_value = """{
            "is_bootstrap": true,
            "framework": "FastAPI",
            "resolved_params": {"python_version": "3.12"},
            "questions": [
                {
                    "key": "package_manager",
                    "question": "Package Manager",
                    "choices": ["1: uv (Recommended)", "2: Poetry"],
                    "default": "uv"
                }
            ]
        }"""
        agent = ClarifierAgent(mock_client)
        result = agent.clarify("Build a high performance FastAPI microservice", interactive=False)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["framework"], "FastAPI")
        self.assertEqual(result["python_version"], "3.12")
        self.assertEqual(result["package_manager"], "uv")

    def test_clarifier_agent_fallback_on_invalid_json(self):
        mock_client = MagicMock()
        # Invalid / unparseable output
        mock_client.generate.return_value = "Sorry, I am just a language model and not JSON."
        agent = ClarifierAgent(mock_client)
        # Should fall back to FrameworkBootstrapClarifier for spring boot
        result = agent.clarify("Creating a hello world spring boot app", interactive=False)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["framework"], "Spring Boot")
        self.assertEqual(result["build_tool"], "Maven")
        self.assertEqual(result["java_version"], "21")

    def test_clarifier_agent_interactive_user_choice(self):
        mock_client = MagicMock()
        mock_client.generate.return_value = """{
            "is_bootstrap": true,
            "framework": "Django",
            "resolved_params": {},
            "questions": [
                {
                    "key": "database",
                    "question": "Database Engine",
                    "choices": ["1: PostgreSQL (Recommended)", "2: SQLite"],
                    "default": "PostgreSQL"
                }
            ]
        }"""
        agent = ClarifierAgent(mock_client)
        prompt_mock = MagicMock(return_value="2")
        result = agent.clarify(
            "Create a new Django site", prompt_ask_fn=prompt_mock, interactive=True
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["framework"], "Django")
        self.assertEqual(result["database"], "SQLite")


if __name__ == "__main__":
    unittest.main()
