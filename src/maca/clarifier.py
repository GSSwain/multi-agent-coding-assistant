"""Framework bootstrap clarification and requirements elicitation."""

import json
from typing import Any, Callable, Dict, List, Optional


class FrameworkBootstrapClarifier:
    """Detects greenfield framework bootstrap tasks and elicits ambiguous

    architectural parameters (build tool, runtime version, language, etc.).
    """

    @staticmethod
    def detect_framework(task_description: str) -> Optional[str]:
        """Detect if the task describes bootstrapping a known framework project."""
        desc_lower = task_description.lower()
        if any(
            kw in desc_lower
            for kw in ["spring boot", "springboot", "spring-boot", "spring microservice"]
        ):
            return "spring_boot"
        if any(
            kw in desc_lower
            for kw in [
                "spring framework",
                "spring mvc",
                "spring context",
                "spring xml",
                "spring bean",
            ]
        ) or ("spring" in desc_lower.split() and "boot" not in desc_lower):
            return "spring_framework"
        if any(kw in desc_lower for kw in ["nextjs", "next.js", "create-next-app"]):
            return "nextjs"
        if any(kw in desc_lower for kw in ["create-react-app", "react app", "react spa"]):
            return "react"
        return None

    @classmethod
    def clarify(
        cls,
        task_description: str,
        prompt_ask_fn: Optional[Callable[..., str]] = None,
        interactive: bool = True,
    ) -> Optional[Dict[str, str]]:
        """Clarify architectural bootstrap parameters for the detected framework."""
        framework = cls.detect_framework(task_description)
        if not framework:
            return None

        if framework == "spring_boot":
            return cls._clarify_spring_boot(task_description, prompt_ask_fn, interactive)
        elif framework == "spring_framework":
            return cls._clarify_spring_framework(task_description, prompt_ask_fn, interactive)
        elif framework == "nextjs":
            return cls._clarify_nextjs(task_description, prompt_ask_fn, interactive)
        elif framework == "react":
            return cls._clarify_react(task_description, prompt_ask_fn, interactive)
        return None

    @classmethod
    def _clarify_spring_boot(
        cls,
        task_description: str,
        prompt_ask_fn: Optional[Callable[..., str]],
        interactive: bool,
    ) -> Dict[str, str]:
        desc_lower = task_description.lower()

        # 1. Build tool
        if "gradle" in desc_lower:
            build_tool = "Gradle (Kotlin DSL)"
        elif "maven" in desc_lower or "pom.xml" in desc_lower:
            build_tool = "Maven"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "\n[bold cyan]Spring Boot Build Tool[/bold cyan] (1: Maven, 2: Gradle)",
                    choices=["1", "2", "Maven", "Gradle"],
                    default="Maven",
                )
                ans_str = str(ans or "").strip().lower()
                build_tool = "Gradle (Kotlin DSL)" if ans_str in ("2", "gradle") else "Maven"
            except Exception:
                build_tool = "Maven"
        else:
            build_tool = "Maven"

        # 2. Java version
        if "17" in desc_lower and "java" in desc_lower:
            java_version = "17"
        elif "21" in desc_lower and "java" in desc_lower:
            java_version = "21"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]Java Version[/bold cyan] (1: Java 21 LTS, 2: Java 17 LTS)",
                    choices=["1", "2", "21", "17"],
                    default="21",
                )
                ans_str = str(ans or "").strip().lower()
                java_version = "17" if ans_str in ("2", "17") else "21"
            except Exception:
                java_version = "21"
        else:
            java_version = "21"

        # 3. Spring Boot version
        if "3.2" in desc_lower:
            spring_boot_version = "3.2.x"
        elif "3.3" in desc_lower:
            spring_boot_version = "3.3.x"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]Spring Boot Version[/bold cyan] (1: 3.3.x, 2: 3.2.x)",
                    choices=["1", "2", "3.3.x", "3.2.x", "3.3", "3.2"],
                    default="3.3.x",
                )
                ans_str = str(ans or "").strip().lower()
                spring_boot_version = "3.2.x" if ans_str in ("2", "3.2", "3.2.x") else "3.3.x"
            except Exception:
                spring_boot_version = "3.3.x"
        else:
            spring_boot_version = "3.3.x"

        # 4. Language
        if "kotlin" in desc_lower:
            language = "Kotlin"
        elif "java" in desc_lower:
            language = "Java"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]Language[/bold cyan] (1: Java, 2: Kotlin)",
                    choices=["1", "2", "Java", "Kotlin"],
                    default="Java",
                )
                ans_str = str(ans or "").strip().lower()
                language = "Kotlin" if ans_str in ("2", "kotlin") else "Java"
            except Exception:
                language = "Java"
        else:
            language = "Java"

        return {
            "framework": "Spring Boot",
            "build_tool": build_tool,
            "java_version": java_version,
            "spring_boot_version": spring_boot_version,
            "language": language,
        }

    @classmethod
    def _clarify_spring_framework(
        cls,
        task_description: str,
        prompt_ask_fn: Optional[Callable[..., str]],
        interactive: bool,
    ) -> Dict[str, str]:
        desc_lower = task_description.lower()

        # Check if user meant Spring Boot vs Classic Spring Framework
        has_explicit_classic = any(
            kw in desc_lower
            for kw in ["classic", "spring framework", "spring-framework", "spring mvc", "xml"]
        )
        if interactive and prompt_ask_fn and not has_explicit_classic:
            try:
                ans = prompt_ask_fn(
                    "\n[bold cyan]Spring Flavor[/bold cyan] (1: Spring Boot [Embedded Server, Starters], 2: Classic Spring Framework [WAR / IoC / MVC])",
                    choices=[
                        "1",
                        "2",
                        "Spring Boot",
                        "Classic Spring Framework",
                        "Spring Framework",
                    ],
                    default="Spring Boot",
                )
                ans_str = str(ans or "").strip().lower()
                if ans_str in ("1", "spring boot", "boot"):
                    return cls._clarify_spring_boot(task_description, prompt_ask_fn, interactive)
            except Exception:
                pass

        # 1. Packaging: WAR vs JAR
        if "war" in desc_lower.split():
            packaging = "WAR (Servlet Container deployment)"
        elif "jar" in desc_lower.split():
            packaging = "JAR (Standalone Spring Context)"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]Packaging[/bold cyan] (1: WAR [Tomcat/Jetty deployment], 2: JAR [Standalone IoC])",
                    choices=["1", "2", "WAR", "JAR"],
                    default="WAR",
                )
                ans_str = str(ans or "").strip().lower()
                packaging = (
                    "JAR (Standalone Spring Context)"
                    if ans_str in ("2", "jar")
                    else "WAR (Servlet Container deployment)"
                )
            except Exception:
                packaging = "WAR (Servlet Container deployment)"
        else:
            packaging = "WAR (Servlet Container deployment)"

        # 2. Configuration Style: Java @Configuration vs XML
        if "xml" in desc_lower:
            config_style = "XML (applicationContext.xml)"
        elif "java" in desc_lower or "@configuration" in desc_lower:
            config_style = "Java Config (@Configuration)"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]Configuration Style[/bold cyan] (1: Java Config [@Configuration], 2: XML [applicationContext.xml])",
                    choices=["1", "2", "Java Config", "XML"],
                    default="Java Config",
                )
                ans_str = str(ans or "").strip().lower()
                config_style = (
                    "XML (applicationContext.xml)"
                    if ans_str in ("2", "xml")
                    else "Java Config (@Configuration)"
                )
            except Exception:
                config_style = "Java Config (@Configuration)"
        else:
            config_style = "Java Config (@Configuration)"

        # 3. Build Tool: Maven vs Gradle
        if "gradle" in desc_lower:
            build_tool = "Gradle"
        elif "maven" in desc_lower or "pom.xml" in desc_lower:
            build_tool = "Maven"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]Build Tool[/bold cyan] (1: Maven, 2: Gradle)",
                    choices=["1", "2", "Maven", "Gradle"],
                    default="Maven",
                )
                ans_str = str(ans or "").strip().lower()
                build_tool = "Gradle" if ans_str in ("2", "gradle") else "Maven"
            except Exception:
                build_tool = "Maven"
        else:
            build_tool = "Maven"

        return {
            "framework": "Spring Framework (Classic)",
            "packaging": packaging,
            "configuration": config_style,
            "build_tool": build_tool,
            "language": "Java",
        }

    @classmethod
    def _clarify_nextjs(
        cls,
        task_description: str,
        prompt_ask_fn: Optional[Callable[..., str]],
        interactive: bool,
    ) -> Dict[str, str]:
        desc_lower = task_description.lower()

        # Language: TypeScript vs JavaScript
        tokens = desc_lower.split()
        if "javascript" in desc_lower or "js" in tokens:
            language = "JavaScript"
        elif "typescript" in desc_lower or "ts" in tokens:
            language = "TypeScript"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "\n[bold cyan]Next.js Language[/bold cyan] (1: TypeScript, 2: JavaScript)",
                    choices=["1", "2", "TypeScript", "JavaScript"],
                    default="TypeScript",
                )
                ans_str = str(ans or "").strip().lower()
                language = "JavaScript" if ans_str in ("2", "javascript") else "TypeScript"
            except Exception:
                language = "TypeScript"
        else:
            language = "TypeScript"

        # Router: App Router vs Pages Router
        if "pages" in desc_lower:
            router = "Pages Router"
        elif "app router" in desc_lower or "app" in desc_lower:
            router = "App Router"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]Next.js Routing[/bold cyan] (1: App Router, 2: Pages Router)",
                    choices=["1", "2", "App Router", "Pages Router"],
                    default="App Router",
                )
                ans_str = str(ans or "").strip().lower()
                router = "Pages Router" if ans_str in ("2", "pages router") else "App Router"
            except Exception:
                router = "App Router"
        else:
            router = "App Router"

        return {
            "framework": "Next.js",
            "language": language,
            "router": router,
        }

    @classmethod
    def _clarify_react(
        cls,
        task_description: str,
        prompt_ask_fn: Optional[Callable[..., str]],
        interactive: bool,
    ) -> Dict[str, str]:
        desc_lower = task_description.lower()

        # Bundler: Vite vs CRA
        if "vite" in desc_lower:
            bundler = "Vite"
        elif "create-react-app" in desc_lower or "cra" in desc_lower.split():
            bundler = "Create React App (CRA)"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "\n[bold cyan]React Tooling / Bundler[/bold cyan] (1: Vite [Recommended], 2: Create React App [Legacy])",
                    choices=["1", "2", "Vite", "CRA", "Create React App"],
                    default="Vite",
                )
                ans_str = str(ans or "").strip().lower()
                bundler = (
                    "Create React App (CRA)"
                    if ans_str in ("2", "cra", "create react app")
                    else "Vite"
                )
            except Exception:
                bundler = "Vite"
        else:
            bundler = "Vite"

        # Language: TypeScript vs JavaScript
        tokens = desc_lower.split()
        if "javascript" in desc_lower or "js" in tokens:
            language = "JavaScript"
        elif "typescript" in desc_lower or "ts" in tokens:
            language = "TypeScript"
        elif interactive and prompt_ask_fn:
            try:
                ans = prompt_ask_fn(
                    "[bold cyan]React Language[/bold cyan] (1: TypeScript, 2: JavaScript)",
                    choices=["1", "2", "TypeScript", "JavaScript"],
                    default="TypeScript",
                )
                ans_str = str(ans or "").strip().lower()
                language = "JavaScript" if ans_str in ("2", "javascript") else "TypeScript"
            except Exception:
                language = "TypeScript"
        else:
            language = "TypeScript"

        return {
            "framework": "React",
            "bundler": bundler,
            "language": language,
        }


def get_mock_clarifier_json(task_description: str) -> str:
    """Generate structured mock JSON for ClarifierAgent in mock/testing mode."""
    framework = FrameworkBootstrapClarifier.detect_framework(task_description)
    if not framework:
        return json.dumps(
            {
                "is_bootstrap": False,
                "framework": None,
                "questions": [],
                "resolved_params": {},
            }
        )

    desc_lower = task_description.lower()
    if framework == "spring_boot":
        resolved: Dict[str, str] = {}
        if "gradle" in desc_lower:
            resolved["build_tool"] = "Gradle (Kotlin DSL)"
        elif "maven" in desc_lower or "pom.xml" in desc_lower:
            resolved["build_tool"] = "Maven"

        if "17" in desc_lower and "java" in desc_lower:
            resolved["java_version"] = "17"
        elif "21" in desc_lower and "java" in desc_lower:
            resolved["java_version"] = "21"

        tokens = desc_lower.split()
        if "kotlin" in tokens:
            resolved["language"] = "Kotlin"
        elif "java" in tokens:
            resolved["language"] = "Java"

        questions: List[Dict[str, Any]] = []
        if "build_tool" not in resolved:
            questions.append(
                {
                    "key": "build_tool",
                    "question": "Spring Boot Build Tool",
                    "choices": ["1: Maven (Recommended)", "2: Gradle (Kotlin DSL)"],
                    "default": "Maven",
                }
            )
        if "java_version" not in resolved:
            questions.append(
                {
                    "key": "java_version",
                    "question": "Java Version",
                    "choices": ["1: Java 21 LTS (Recommended)", "2: Java 17 LTS"],
                    "default": "21",
                }
            )
        if "spring_boot_version" not in resolved:
            questions.append(
                {
                    "key": "spring_boot_version",
                    "question": "Spring Boot Version",
                    "choices": ["1: 3.3.x (Recommended)", "2: 3.2.x"],
                    "default": "3.3.x",
                }
            )
        if "language" not in resolved:
            questions.append(
                {
                    "key": "language",
                    "question": "Programming Language",
                    "choices": ["1: Java (Recommended)", "2: Kotlin"],
                    "default": "Java",
                }
            )

        return json.dumps(
            {
                "is_bootstrap": True,
                "framework": "Spring Boot",
                "resolved_params": resolved,
                "questions": questions,
            }
        )

    elif framework == "spring_framework":
        resolved = {}
        if "gradle" in desc_lower:
            resolved["build_tool"] = "Gradle"
        elif "maven" in desc_lower or "pom.xml" in desc_lower:
            resolved["build_tool"] = "Maven"

        tokens = desc_lower.split()
        if "xml" in tokens:
            resolved["configuration"] = "XML (applicationContext.xml)"
        elif "java" in desc_lower and "config" in desc_lower:
            resolved["configuration"] = "Java Config (@Configuration)"

        if "war" in tokens:
            resolved["packaging"] = "WAR (Servlet Container deployment)"
        elif "jar" in tokens:
            resolved["packaging"] = "Standalone JAR"

        questions = []
        if "packaging" not in resolved:
            questions.append(
                {
                    "key": "packaging",
                    "question": "Packaging",
                    "choices": [
                        "1: WAR (Servlet Container deployment) (Recommended)",
                        "2: Standalone JAR",
                    ],
                    "default": "WAR (Servlet Container deployment)",
                }
            )
        if "configuration" not in resolved:
            questions.append(
                {
                    "key": "configuration",
                    "question": "Configuration Style",
                    "choices": [
                        "1: Java Config (@Configuration) (Recommended)",
                        "2: XML (applicationContext.xml)",
                    ],
                    "default": "Java Config (@Configuration)",
                }
            )
        if "build_tool" not in resolved:
            questions.append(
                {
                    "key": "build_tool",
                    "question": "Build Tool",
                    "choices": ["1: Maven (Recommended)", "2: Gradle"],
                    "default": "Maven",
                }
            )

        return json.dumps(
            {
                "is_bootstrap": True,
                "framework": "Spring Framework (Classic)",
                "resolved_params": resolved,
                "questions": questions,
            }
        )

    elif framework == "nextjs":
        resolved = {}
        tokens = desc_lower.split()
        if "typescript" in desc_lower or "ts" in tokens:
            resolved["language"] = "TypeScript"
        elif "javascript" in desc_lower or "js" in tokens:
            resolved["language"] = "JavaScript"

        if "pages" in desc_lower:
            resolved["router"] = "Pages Router"
        elif "app" in desc_lower:
            resolved["router"] = "App Router"

        questions = []
        if "language" not in resolved:
            questions.append(
                {
                    "key": "language",
                    "question": "Language",
                    "choices": ["1: TypeScript (Recommended)", "2: JavaScript"],
                    "default": "TypeScript",
                }
            )
        if "router" not in resolved:
            questions.append(
                {
                    "key": "router",
                    "question": "Routing Architecture",
                    "choices": ["1: App Router (Recommended)", "2: Pages Router"],
                    "default": "App Router",
                }
            )

        return json.dumps(
            {
                "is_bootstrap": True,
                "framework": "Next.js",
                "resolved_params": resolved,
                "questions": questions,
            }
        )

    elif framework == "react":
        resolved = {}
        tokens = desc_lower.split()
        if "create-react-app" in desc_lower or "cra" in tokens:
            resolved["bundler"] = "Create React App (CRA)"
        elif "vite" in desc_lower:
            resolved["bundler"] = "Vite"

        if "typescript" in desc_lower or "ts" in tokens:
            resolved["language"] = "TypeScript"
        elif "javascript" in desc_lower or "js" in tokens:
            resolved["language"] = "JavaScript"

        questions = []
        if "bundler" not in resolved:
            questions.append(
                {
                    "key": "bundler",
                    "question": "Tooling & Bundler",
                    "choices": ["1: Vite (Recommended)", "2: Create React App (CRA)"],
                    "default": "Vite",
                }
            )
        if "language" not in resolved:
            questions.append(
                {
                    "key": "language",
                    "question": "Language",
                    "choices": ["1: TypeScript (Recommended)", "2: JavaScript"],
                    "default": "TypeScript",
                }
            )

        return json.dumps(
            {
                "is_bootstrap": True,
                "framework": "React",
                "resolved_params": resolved,
                "questions": questions,
            }
        )

    return json.dumps(
        {
            "is_bootstrap": False,
            "framework": None,
            "questions": [],
            "resolved_params": {},
        }
    )
