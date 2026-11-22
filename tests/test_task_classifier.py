import unittest
from unittest.mock import MagicMock

from maca.agents.task_classifier import TaskClassifierAgent


class TestTaskClassifierAgent(unittest.TestCase):
    def setUp(self):
        self.agent = TaskClassifierAgent()
        # Replace the real evaluator with a mock
        self.mock_evaluator = MagicMock()
        self.agent.evaluator = self.mock_evaluator

    def test_classify_simple(self):
        self.mock_evaluator.evaluate.return_value = "SIMPLE"
        result = self.agent.classify("Write a hello world script")
        self.assertEqual(result, "SIMPLE")
        self.mock_evaluator.evaluate.assert_called_once_with("Write a hello world script")

    def test_classify_complex(self):
        self.mock_evaluator.evaluate.return_value = "COMPLEX"
        result = self.agent.classify("Implement a transformer model for language generation")
        self.assertEqual(result, "COMPLEX")
        self.mock_evaluator.evaluate.assert_called_once_with(
            "Implement a transformer model for language generation"
        )

    def test_classify_spring_boot_app_real_evaluator(self):
        real_agent = TaskClassifierAgent()
        with unittest.mock.patch.object(
            real_agent.evaluator.gemma_client, "generate", side_effect=Exception("offline")
        ):
            result = real_agent.classify("Creating a hello world spring boot app")
        self.assertEqual(result, "COMPLEX")


if __name__ == "__main__":
    unittest.main()
