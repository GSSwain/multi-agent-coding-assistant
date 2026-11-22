import ast
import pathlib
import unittest


class TestNoCrossAgentCalls(unittest.TestCase):
    def test_no_cross_agent_calls(self):
        """Ensure that *only* ``src/maca/orchestrator.py`` uses the ``call_agent`` helper.

        The architecture mandates that the ``Orchestrator`` is the sole coordinator of
        sub‑agents via the ``a2a_call_helper.call_agent`` function. All other agent
        modules should be self‑contained and must not invoke ``call_agent`` directly.
        """
        src_root = pathlib.Path("src/maca")
        for py_file in src_root.rglob("*.py"):
            if py_file.name in ("orchestrator.py", "a2a_call_helper.py"):
                continue
            tree = ast.parse(py_file.read_text())
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "call_agent"
                ):
                    self.fail(
                        f"{py_file.relative_to(src_root)} calls call_agent directly; agents should not invoke each other without the orchestrator."
                    )


if __name__ == "__main__":
    unittest.main()
