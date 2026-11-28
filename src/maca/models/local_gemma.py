import json
import os
import re
import shutil
import subprocess
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from maca import maca_config as config

_CONTEXT_WINDOW_CACHE: Dict[Tuple[str, str], Optional[int]] = {}
_NUM_CTX_PATTERN = re.compile(r"\bnum_ctx\s+(\d+)\b")


def _get_ollama_num_ctx_env() -> Optional[int]:
    """Return positive OLLAMA_NUM_CTX env override if configured."""
    raw = os.environ.get("OLLAMA_NUM_CTX")
    if raw is None or not raw.strip():
        return None
    try:
        parsed = int(raw.strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _get_effective_ollama_num_ctx() -> Optional[int]:
    """Return active Ollama num_ctx cap from env override or resolved config."""
    env_ctx = _get_ollama_num_ctx_env()
    if env_ctx is not None:
        return env_ctx
    cfg_ctx = getattr(config, "OLLAMA_NUM_CTX", 0)
    if isinstance(cfg_ctx, int) and not isinstance(cfg_ctx, bool) and cfg_ctx > 0:
        return cfg_ctx
    return None


def _parse_ollama_show_context_window(payload: Any) -> Optional[int]:
    """Extract allowed context length from an Ollama /api/show JSON payload."""
    if not isinstance(payload, dict):
        return None

    candidates: List[int] = []

    model_info = payload.get("model_info")
    if isinstance(model_info, dict):
        for key, value in model_info.items():
            if isinstance(key, str) and key.endswith(".context_length"):
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    candidates.append(value)

    parameters = payload.get("parameters")
    if isinstance(parameters, str):
        for match in _NUM_CTX_PATTERN.finditer(parameters):
            token_str = match.group(1)
            if token_str.isascii() and token_str.isdigit():
                parsed_ctx = int(token_str)
                if parsed_ctx > 0:
                    candidates.append(parsed_ctx)

    if not candidates:
        return None
    return min(candidates)


class LocalGemmaClient:
    def __init__(self):
        self.url = config.OLLAMA_API_URL
        self.model = config.OLLAMA_MODEL

    @classmethod
    def clear_context_window_cache(cls) -> None:
        """Clear cached Ollama context window lookups."""
        _CONTEXT_WINDOW_CACHE.clear()

    def get_context_window(self) -> int:
        """Discover the allowed context window for this local Ollama model."""
        env_num_ctx = _get_ollama_num_ctx_env()
        if config.MOCK_GEMMA_FALLBACK:
            if env_num_ctx is not None:
                return env_num_ctx
            return int(config.CONTEXT_TOKEN_BUDGET)

        cache_key: Tuple[str, str] = (str(self.url), str(self.model))
        if cache_key in _CONTEXT_WINDOW_CACHE:
            discovered = _CONTEXT_WINDOW_CACHE[cache_key]
        else:
            try:
                show_url = f"{str(self.url).rstrip('/')}/api/show"
                req = urllib.request.Request(
                    show_url,
                    data=json.dumps({"name": self.model}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                discovered = _parse_ollama_show_context_window(payload)
            except Exception:
                discovered = None
            _CONTEXT_WINDOW_CACHE[cache_key] = discovered

        effective_num_ctx = _get_effective_ollama_num_ctx()
        if discovered is not None and effective_num_ctx is not None:
            return min(discovered, effective_num_ctx)
        if discovered is not None:
            return discovered
        if env_num_ctx is not None:
            return env_num_ctx
        return int(config.CONTEXT_TOKEN_BUDGET)

    def generate(self, prompt, system_instruction=""):
        if config.MOCK_GEMMA_FALLBACK:
            return self._generate_mock(prompt, system_instruction)

        # Combine system instruction and prompt
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\\n\\nTask: {prompt}"

        # 1. Try HTTP API
        try:
            payload: Dict[str, Any] = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
            }
            if config.OLLAMA_NUM_CTX > 0:
                payload["options"] = {"num_ctx": config.OLLAMA_NUM_CTX}
            req = urllib.request.Request(
                f"{self.url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode("utf-8"))
                return res.get("response", "")
        except Exception as e:
            # 2. Try Subprocess CLI
            try:
                # Run: ollama run model "prompt"
                # We pass prompt through stdin to avoid command line length limits
                ollama_exe = shutil.which("ollama") or "ollama"
                res = subprocess.run(
                    [ollama_exe, "run", self.model],
                    input=full_prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                if res.returncode == 0:
                    return res.stdout.strip()
            except FileNotFoundError:
                pass
            except Exception:
                pass

            # 3. Try Mock Fallback
            if config.MOCK_GEMMA_FALLBACK:
                return self._generate_mock(prompt, system_instruction)

            raise RuntimeError(f"Failed to connect to local Gemma via Ollama API and CLI: {e}")

    def _generate_mock(self, prompt, system_instruction):
        prompt_lower = prompt.lower()
        sys_lower = system_instruction.lower()
        is_spring_boot = any(
            kw in prompt_lower for kw in ["springboot", "spring boot", "spring-boot"]
        )
        is_spring_framework = "spring" in prompt_lower and not is_spring_boot
        is_plain_java = "java" in prompt_lower and not (is_spring_boot or is_spring_framework)

        if "clarifier" in sys_lower:
            from maca.clarifier import get_mock_clarifier_json

            return get_mock_clarifier_json(prompt)

        if "coder" in sys_lower:
            if is_spring_boot:
                if "gradle" in prompt_lower:
                    build_file = """[FILE: build.gradle.kts]
```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.0"
    id("io.spring.dependency-management") version "1.1.5"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```"""
                else:
                    build_file = """[FILE: pom.xml]
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>demo</name>
    <description>Demo project for Spring Boot</description>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
```"""
                java_file = """[FILE: src/main/java/com/example/demo/DemoApplication.java]
```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/")
    public String hello() {
        return "Hello World from Spring Boot!";
    }
}
```"""
                return build_file + "\n\n" + java_file
            elif is_spring_framework:
                build_file = """[FILE: pom.xml]
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>demo-spring</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.10</version>
        </dependency>
    </dependencies>
</project>
```"""
                java_file = """[FILE: src/main/java/com/example/demo/AppConfig.java]
```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AppConfig {

    @Bean
    public String message() {
        return "Hello from Spring Framework!";
    }
}
```"""
                return build_file + "\n\n" + java_file
            elif is_plain_java:
                return """[FILE: src/main/java/com/example/Main.java]
```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from Java!");
    }
}
```"""
            return """[FILE: output_gemma.py]
```python
# Generated by Local Gemma Agent
def main():
    print("Hello from local Gemma agent!")

if __name__ == "__main__":
    main()
```"""
        elif "reviewer" in sys_lower:
            return """# Code Review
- Syntax check: PASSED
- Correctness check: PASSED
APPROVED."""
        else:
            if is_spring_boot:
                build_item = "build.gradle.kts" if "gradle" in prompt_lower else "pom.xml"
                return f"""# Implementation Plan
1. [NEW] Create `{build_item}` with Spring Boot dependencies.
2. [NEW] Create `src/main/java/com/example/demo/DemoApplication.java` with Spring Boot REST controller.
3. Verify Spring Boot build and endpoint.
"""
            elif is_spring_framework:
                build_item = "build.gradle" if "gradle" in prompt_lower else "pom.xml"
                return f"""# Implementation Plan
1. [NEW] Create `{build_item}` with Spring Framework dependencies (spring-context).
2. [NEW] Create `src/main/java/com/example/demo/AppConfig.java` with Spring @Configuration.
3. Verify Spring context initialization.
"""
            elif is_plain_java:
                return """# Implementation Plan
1. [NEW] Create `src/main/java/com/example/Main.java` with application logic.
2. Run sanity check.
"""
            return """# Implementation Plan
1. [NEW] Create `output_gemma.py` with code logic.
2. Run sanity check.
"""
