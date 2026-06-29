import unittest
from unittest.mock import MagicMock

from maca.agents.coder import SimpleCoderAgent, SpecCoderAgent
from maca.agents.reviewer import ReviewerAgent
from maca.agents.spec import SpecAgent


class TestAgentsPrompts(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.simple_coder = SimpleCoderAgent("SimpleCoder", self.mock_client)
        self.spec_coder = SpecCoderAgent("SpecCoder", self.mock_client)
        self.spec_agent = SpecAgent(self.mock_client)
        self.reviewer = ReviewerAgent(self.mock_client)

    def test_simple_coder_system_instruction_clean_code(self):
        sys_inst = self.simple_coder._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE GUIDELINES", sys_inst)
        self.assertIn("Modularity", sys_inst)
        self.assertIn("Type Safety", sys_inst)

    def test_simple_coder_prompt_clean_code(self):
        prompt = self.simple_coder._build_prompt("test task", "test plan", {}, [])
        self.assertIn("clean code principles", prompt)

    def test_spec_coder_system_instruction_clean_code(self):
        sys_inst = self.spec_coder._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE GUIDELINES", sys_inst)
        self.assertIn("Modularity", sys_inst)
        self.assertIn("Type Safety", sys_inst)

    def test_spec_coder_prompt_clean_code(self):
        prompt = self.spec_coder._build_prompt("test task", "test spec", {}, [])
        self.assertIn("clean code principles", prompt)

    def test_spec_agent_system_instruction(self):
        sys_inst = self.spec_agent._build_system_instruction()
        self.assertIn("Technical Specification Agent", sys_inst)
        self.assertIn("detailed technical specification", sys_inst)

    def test_spec_agent_prompt(self):
        prompt = self.spec_agent._build_prompt("test task", "test plan", [])
        self.assertIn("test task", prompt)
        self.assertIn("Implementation Plan:", prompt)

    def test_reviewer_system_instruction_clean_code(self):
        sys_inst = self.reviewer._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE AUDITING CRITERIA", sys_inst)
        self.assertIn("Readability & Naming", sys_inst)
        self.assertIn("Single Responsibility", sys_inst)

    def test_reviewer_prompt_clean_code(self):
        prompt_no_spec = self.reviewer._build_prompt("test task", {}, [])
        self.assertIn("clean code practices", prompt_no_spec)
        self.assertNotIn("Implementation Plan/Specification:", prompt_no_spec)

        prompt_with_spec = self.reviewer._build_prompt("test task", {}, [], "test plan content")
        self.assertIn("clean code practices", prompt_with_spec)
        self.assertIn("Implementation Plan/Specification:", prompt_with_spec)
        self.assertIn("test plan content", prompt_with_spec)

    def test_reviewer_is_approved(self):
        self.assertTrue(self.reviewer.is_approved("Looks perfect. APPROVED."))
        self.assertTrue(self.reviewer.is_approved("approved"))
        self.assertFalse(self.reviewer.is_approved("Issues found: missing docstring. REJECTED."))
        self.assertFalse(self.reviewer.is_approved("No approval given."))
