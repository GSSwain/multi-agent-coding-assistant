from maca.models.local_gemma import LocalGemmaClient


class ComplexityEvaluator:
    def __init__(self):
        self.gemma_client = LocalGemmaClient()

    def evaluate(self, prompt):
        # 1. Try evaluating with local Gemma
        try:
            system_instruction = (
                "You are an AI task routing agent. Classify the user task into one of the following complexity levels: "
                "SIMPLE, MEDIUM, COMPLEX, VERY_COMPLEX. "
                "Respond with EXACTLY ONE WORD from those four choices, nothing else."
            )
            gemma_prompt = (
                "Categories:\\n"
                "- SIMPLE: Basic scripts, simple functions, CLI output, formatting.\\n"
                "- MEDIUM: Small modular script, simple files, basic APIs, simple unit tests.\\n"
                "- COMPLEX: Multi-file project, third-party libraries, APIs, DB integration, scraper.\\n"
                "- VERY_COMPLEX: Multi-threaded DB from scratch, AST parser, distributed system, cryptography.\\n\\n"
                f"Task: {prompt}\\n\\n"
                "Classification (SIMPLE, MEDIUM, COMPLEX, or VERY_COMPLEX):"
            )
            response = self.gemma_client.generate(gemma_prompt, system_instruction).strip().upper()

            # Extract the keyword from response
            for val in ["VERY_COMPLEX", "COMPLEX", "MEDIUM", "SIMPLE"]:
                if val in response:
                    return val
        except Exception:
            pass

        # 2. Heuristic fallback
        return self._heuristic_evaluate(prompt)

    def _heuristic_evaluate(self, prompt):
        prompt_lower = prompt.lower()

        # Very Complex Indicators
        very_complex_keywords = [
            "distributed",
            "concurrency",
            "multi-thread",
            "thread-safe",
            "acid",
            "replicat",
            "ast parser",
            "lexer",
            "compiler",
            "interpreter",
            "cryptography",
            "blockchain",
            "transaction log",
            "race condition",
            "consensus",
            "raft",
            "paxos",
            "from scratch",
        ]
        if any(kw in prompt_lower for kw in very_complex_keywords):
            return "VERY_COMPLEX"

        # Complex Indicators
        complex_keywords = [
            "database",
            "sql",
            "api",
            "scraper",
            "beautifulsoup",
            "selenium",
            "web server",
            "flask",
            "django",
            "fastapi",
            "express",
            "multi-file",
            "integration",
            "docker",
            "pipeline",
            "regex",
            "pandas",
            "matplotlib",
        ]
        if any(kw in prompt_lower for kw in complex_keywords) or len(prompt.split()) > 40:
            return "COMPLEX"

        # Default to SIMPLE or MEDIUM
        if len(prompt.split()) > 15:
            return "MEDIUM"
        return "SIMPLE"
