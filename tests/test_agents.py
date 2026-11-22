import unittest
from unittest.mock import MagicMock

from maca.agents.clarifier import ClarifierAgent
from maca.agents.coder import SimpleCoderAgent, SpecCoderAgent
from maca.agents.planner import PlannerAgent
from maca.agents.reviewer import ReviewerAgent
from maca.agents.spec import SpecAgent


class TestAgentsPrompts(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.simple_coder = SimpleCoderAgent("SimpleCoder", self.mock_client)
        self.spec_coder = SpecCoderAgent("SpecCoder", self.mock_client)
        self.spec_agent = SpecAgent(self.mock_client)
        self.reviewer = ReviewerAgent(self.mock_client)
        self.planner = PlannerAgent(self.mock_client)
        self.clarifier = ClarifierAgent(self.mock_client)

    def test_simple_coder_system_instruction_clean_code(self):
        sys_inst = self.simple_coder._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE GUIDELINES", sys_inst)
        self.assertIn("Modularity", sys_inst)
        self.assertIn("Type Safety", sys_inst)
        self.assertIn("LANGUAGE & FRAMEWORK FIDELITY", sys_inst)
        self.assertIn("NEVER generate Python code", sys_inst)

    def test_simple_coder_prompt_clean_code(self):
        prompt = self.simple_coder._build_prompt("test task", "test plan", {}, [])
        self.assertIn("clean code principles", prompt)
        self.assertIn("requested programming language", prompt)

    def test_spec_coder_system_instruction_clean_code(self):
        sys_inst = self.spec_coder._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE GUIDELINES", sys_inst)
        self.assertIn("Modularity", sys_inst)
        self.assertIn("Type Safety", sys_inst)
        self.assertIn("LANGUAGE & FRAMEWORK FIDELITY", sys_inst)
        self.assertIn("NEVER generate Python code", sys_inst)

    def test_spec_coder_prompt_clean_code(self):
        prompt = self.spec_coder._build_prompt("test task", "test spec", {}, [])
        self.assertIn("clean code principles", prompt)
        self.assertIn("requested programming language", prompt)

    def test_spec_agent_system_instruction(self):
        sys_inst = self.spec_agent._build_system_instruction()
        self.assertIn("Technical Specification Agent", sys_inst)
        self.assertIn("detailed technical specification", sys_inst)
        self.assertIn("LANGUAGE & FRAMEWORK FIDELITY", sys_inst)

    def test_spec_agent_prompt(self):
        prompt = self.spec_agent._build_prompt("test task", "test plan", [])
        self.assertIn("test task", prompt)
        self.assertIn("Implementation Plan:", prompt)
        self.assertIn("requested language", prompt)

    def test_reviewer_system_instruction_clean_code(self):
        sys_inst = self.reviewer._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE AUDITING CRITERIA", sys_inst)
        self.assertIn("Readability & Naming", sys_inst)
        self.assertIn("Single Responsibility", sys_inst)
        self.assertIn("Language & Framework Conformance", sys_inst)

    def test_reviewer_prompt_clean_code(self):
        prompt_no_spec = self.reviewer._build_prompt("test task", {}, [])
        self.assertIn("clean code practices", prompt_no_spec)
        self.assertNotIn("Implementation Plan/Specification:", prompt_no_spec)

        prompt_with_spec = self.reviewer._build_prompt("test task", {}, [], "test plan content")
        self.assertIn("clean code practices", prompt_with_spec)
        self.assertIn("Implementation Plan/Specification:", prompt_with_spec)
        self.assertIn("test plan content", prompt_with_spec)

    def test_reviewer_prompt_with_file_blocks(self):
        file_blocks = {
            "main.py": [
                {"start_line": 10, "end_line": 20, "tag": "modified", "code": "def hello(): pass\n"}
            ]
        }
        prompt = self.reviewer._build_prompt(
            "test task",
            {"main.py": "def hello(): pass\n"},
            [],
            "test plan",
            file_blocks=file_blocks,
        )
        self.assertIn("Target File and Line Blocks to Review:", prompt)
        self.assertIn("--- FILE: main.py ---", prompt)
        self.assertIn("[Block: Lines 10-20 (modified)]", prompt)
        self.assertIn("def hello(): pass", prompt)

    def test_coder_compute_file_blocks(self):
        blocks = self.simple_coder.compute_file_blocks(
            {"new_file.py": "line 1\nline 2\n"},
            repo_files_content={},
        )
        self.assertIn("new_file.py", blocks)
        self.assertEqual(blocks["new_file.py"][0]["start_line"], 1)
        self.assertEqual(blocks["new_file.py"][0]["end_line"], 2)

    def test_planner_agent_system_instruction(self):
        sys_inst = self.planner._build_system_instruction()
        self.assertIn("Planner Agent", sys_inst)
        self.assertIn("structured markdown implementation plan", sys_inst)
        self.assertIn("LANGUAGE & FRAMEWORK FIDELITY", sys_inst)

    def test_planner_agent_prompt(self):
        prompt = self.planner._build_prompt("test task", ["file1.java"], [])
        self.assertIn("test task", prompt)
        self.assertIn("file1.java", prompt)
        self.assertIn("target programming language and framework", prompt)

    def test_reviewer_is_approved(self):
        self.assertTrue(self.reviewer.is_approved("Looks perfect. APPROVED."))
        self.assertTrue(self.reviewer.is_approved("approved"))
        self.assertFalse(self.reviewer.is_approved("Issues found: missing docstring. REJECTED."))
        self.assertFalse(self.reviewer.is_approved("No approval given."))

    def test_clarifier_agent_system_instruction(self):
        sys_inst = self.clarifier._build_system_instruction()
        self.assertIn("Architecture Clarifier Agent", sys_inst)
        self.assertIn("is_bootstrap", sys_inst)
        self.assertIn("resolved_params", sys_inst)

    def test_clarifier_agent_prompt(self):
        prompt = self.clarifier._build_prompt("Create a FastAPI backend with Postgres")
        self.assertIn("Create a FastAPI backend with Postgres", prompt)
        self.assertIn("framework bootstrapping", prompt)

    def test_clarifier_agent_llm_json_flow(self):
        self.mock_client.generate.return_value = """```json
        {
            "is_bootstrap": true,
            "framework": "FastAPI",
            "resolved_params": {"language": "Python"},
            "questions": [
                {
                    "key": "package_manager",
                    "question": "Package Manager",
                    "choices": ["1: uv (Recommended)", "2: Poetry"],
                    "default": "uv"
                }
            ]
        }
        ```"""
        result = self.clarifier.clarify(
            "Create a FastAPI backend with Postgres",
            prompt_ask_fn=lambda prompt, choices, default: "1",
            interactive=True,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["framework"], "FastAPI")
        self.assertEqual(result["language"], "Python")
        self.assertEqual(result["package_manager"], "uv")
