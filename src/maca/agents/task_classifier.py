from maca.evaluator import ComplexityEvaluator


class TaskClassifierAgent:
    """Agent responsible for classifying task complexity.

    It encapsulates the ComplexityEvaluator logic and provides a simple
    interface for the Orchestrator to obtain the task classification.
    """

    def __init__(self) -> None:
        self.evaluator = ComplexityEvaluator()

    def classify(self, task_description: str) -> str:
        """Return the complexity classification for the given task.

        Possible return values: "SIMPLE", "MEDIUM", "COMPLEX", "VERY_COMPLEX".
        """
        return str(self.evaluator.evaluate(task_description))

    def evaluate(self, task_description: str) -> str:
        """Alias for classify to support backward compatibility."""
        return self.classify(task_description)

    @property
    def gemma_client(self):
        return getattr(self.evaluator, "gemma_client", None)


if __name__ == "__main__":
    import json
    import sys

    payload = json.loads(sys.stdin.read())
    args = payload.get("args", {})
    context = args.get("context")
    task_description = args.get("task_description", "")
    if context and not task_description:
        task_description = context.get("task", "")
    agent = TaskClassifierAgent()
    complexity = agent.classify(task_description)
    json.dump(
        {
            "result": complexity,
            "agent": "task_classifier",
            "completed": True,
            "update": {"complexity": complexity},
        },
        sys.stdout,
    )
