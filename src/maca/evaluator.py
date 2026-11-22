from maca.models.local_gemma import LocalGemmaClient

FRAMEWORK_KEYWORDS = [
    "spring",
    "spring boot",
    "springboot",
    "spring-boot",
    "maven",
    "gradle",
    "pom.xml",
    "build.gradle",
    "quarkus",
    "micronaut",
    "react",
    "vue",
    "angular",
    "svelte",
    "next.js",
    "nextjs",
    "nuxt",
    "nestjs",
    "rails",
    "ruby on rails",
    "laravel",
    "asp.net",
    ".net",
    "dotnet",
    "blazor",
    "microservice",
    "web server",
    "flask",
    "django",
    "fastapi",
    "express",
    "gin",
    "actix",
    "rocket",
]


class ComplexityEvaluator:
    def __init__(self):
        self.gemma_client = LocalGemmaClient()

    def evaluate(self, prompt):
        prompt_lower = prompt.lower()
        is_framework_task = any(kw in prompt_lower for kw in FRAMEWORK_KEYWORDS)

        # 1. Try evaluating with local Gemma
        try:
            system_instruction = (
                "You are an AI task routing agent. Classify the user task into one of the following complexity levels: "
                "SIMPLE, MEDIUM, COMPLEX, VERY_COMPLEX. "
                "Respond with EXACTLY ONE WORD from those four choices, nothing else."
            )
            gemma_prompt = (
                "Categories:\n"
                "- SIMPLE: Single-file scripts, basic utility functions, simple algorithms, CLI formatting.\n"
                "- MEDIUM: Small modular script (1-2 files), basic unit tests, simple CLI tools.\n"
                "- COMPLEX: Application frameworks (Spring Boot, Django, React, NestJS, Rails), multi-file projects, third-party libraries/build tools (Maven, Gradle, npm), APIs, DB integration, web servers, scrapers.\n"
                "- VERY_COMPLEX: Multi-threaded DB from scratch, AST parser, distributed system, cryptography, compilers.\n\n"
                "Rule: Any task requesting an application framework project (e.g. Spring Boot, Django, Rails, React) or build scaffolding (Maven, Gradle, npm) is COMPLEX, never SIMPLE, even for hello-world or starter apps.\n\n"
                f"Task: {prompt}\n\n"
                "Classification (SIMPLE, MEDIUM, COMPLEX, or VERY_COMPLEX):"
            )
            response = self.gemma_client.generate(gemma_prompt, system_instruction).strip().upper()

            # Extract the keyword from response
            for val in ["VERY_COMPLEX", "COMPLEX", "MEDIUM", "SIMPLE"]:
                if val in response:
                    # Guardrail: Application framework projects require multi-file scaffolding
                    # and must never be downgraded to SIMPLE by a small model.
                    if val == "SIMPLE" and is_framework_task:
                        return "COMPLEX"
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

        # Framework and application scaffolding are always at least COMPLEX
        if any(kw in prompt_lower for kw in FRAMEWORK_KEYWORDS):
            return "COMPLEX"

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
            "microservice",
            "rest api",
            "restful",
            "crud",
        ]
        if any(kw in prompt_lower for kw in complex_keywords) or len(prompt.split()) > 40:
            return "COMPLEX"

        # Default to SIMPLE or MEDIUM
        if len(prompt.split()) > 15:
            return "MEDIUM"
        return "SIMPLE"
