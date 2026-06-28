import unittest
from unittest.mock import MagicMock

from maca.agents.coder import CoderAgent
from maca.agents.reviewer import ReviewerAgent


class TestAgentsPrompts(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.coder = CoderAgent("Coder", self.mock_client)
        self.reviewer = ReviewerAgent(self.mock_client)

    def test_coder_system_instruction_clean_code(self):
        sys_inst = self.coder._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE GUIDELINES", sys_inst)
        self.assertIn("Modularity", sys_inst)
        self.assertIn("Type Safety", sys_inst)

    def test_coder_prompt_clean_code(self):
        prompt = self.coder._build_prompt("test task", "test plan", {}, [])
        self.assertIn("clean code principles", prompt)

    def test_reviewer_system_instruction_clean_code(self):
        sys_inst = self.reviewer._build_system_instruction()
        self.assertIn("clean code practices", sys_inst)
        self.assertIn("CLEAN CODE AUDITING CRITERIA", sys_inst)
        self.assertIn("Readability & Naming", sys_inst)
        self.assertIn("Single Responsibility", sys_inst)

    def test_reviewer_prompt_clean_code(self):
        prompt = self.reviewer._build_prompt("test task", {}, [])
        self.assertIn("clean code practices", prompt)
