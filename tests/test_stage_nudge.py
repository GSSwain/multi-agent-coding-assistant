import unittest
from unittest import mock

from maca.stages.nudge import NudgeLoopRunner


class TestStageNudge(unittest.TestCase):
    def test_run_nudge_iteration_with_updates(self):
        mock_coder = mock.MagicMock(return_value=({"file.py": "print(1)"}, {}, "response"))
        mock_apply = mock.MagicMock(return_value={"file.py": [{"tag": "created"}]})

        result = NudgeLoopRunner.run_nudge_iteration(
            run_coder_fn=mock_coder,
            apply_update_fn=mock_apply,
            nudge_prompt="Fix error",
            nudge_label="fix error",
            spinner_message="Applying fixes...",
            persist_changes=True,
            custom_arg="hello",
        )

        mock_coder.assert_called_once_with(custom_arg="hello", nudge="Fix error")
        mock_apply.assert_called_once_with(
            updated_files={"file.py": "print(1)"},
            summary_label="fix error",
            persist_changes=True,
        )
        self.assertEqual(result, {"file.py": [{"tag": "created"}]})

    def test_run_nudge_iteration_empty_updates(self):
        mock_coder = mock.MagicMock(return_value=({}, {}, "no updates"))
        mock_apply = mock.MagicMock()

        result = NudgeLoopRunner.run_nudge_iteration(
            run_coder_fn=mock_coder,
            apply_update_fn=mock_apply,
            nudge_prompt="Retry",
            nudge_label="retry",
            spinner_message="Retrying...",
            persist_changes=False,
        )

        mock_coder.assert_called_once()
        mock_apply.assert_not_called()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
