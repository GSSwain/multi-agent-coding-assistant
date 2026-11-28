import json
import urllib.error
import urllib.request

from maca import maca_config as config


class ClaudeClient:
    def __init__(self):
        self.api_key = config.get_claude_api_key()
        self.model = config.CLAUDE_MODEL
        self.timeout = config.CLAUDE_TIMEOUT_SECONDS

    def get_context_window(self) -> int:
        """Return the configured context window for Claude models."""
        return int(config.CLAUDE_CONTEXT_WINDOW)

    def generate(self, prompt, system_instruction=""):
        if not self.api_key:
            if config.MOCK_GEMMA_FALLBACK:
                return self._generate_mock(prompt, system_instruction)
            raise ValueError("CLAUDE_API_KEY is not set.")

        url = "https://api.anthropic.com/v1/messages"

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system_instruction:
            payload["system"] = system_instruction

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        # Setup secure SSL context using certifi if available
        import ssl

        try:
            import certifi

            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ssl_context = ssl.create_default_context()

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout, context=ssl_context) as response:
                res = json.loads(response.read().decode("utf-8"))
                # Extract response text from the Messages API response
                content_blocks = res.get("content", [])
                if content_blocks:
                    # Concatenate all text blocks
                    texts = [
                        block.get("text", "")
                        for block in content_blocks
                        if block.get("type") == "text"
                    ]
                    if texts:
                        return "\n".join(texts)
                return "Error: Empty response from Claude."
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                err_json = json.loads(error_body)
                msg = err_json.get("error", {}).get("message", error_body)
                err_type = err_json.get("error", {}).get("type", "")
                err_msg = f"{err_type}: {msg}"
            except Exception:
                err_msg = error_body
            if config.MOCK_GEMMA_FALLBACK:
                return self._generate_mock(prompt, system_instruction)
            raise RuntimeError(f"Claude API request failed (HTTP {e.code}): {err_msg}")
        except Exception as e:
            if config.MOCK_GEMMA_FALLBACK:
                return self._generate_mock(prompt, system_instruction)
            raise RuntimeError(f"Claude API request failed: {e}")

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
            return """[FILE: output_claude.py]
```python
# Generated by Claude Agent (Mocked)
import urllib.request
import json


def fetch_url(url):
    print(f"Fetching: {url}")
    try:
        with urllib.request.urlopen(url) as res:
            return res.read().decode("utf-8")
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    content = fetch_url("https://httpbin.org/get")
    print(content[:200])
```"""
        elif "reviewer" in sys_lower:
            return """# Code Review (Claude Mocked)
- Syntax checks: PASSED
APPROVED."""
        else:
            if is_spring_boot:
                build_item = "build.gradle.kts" if "gradle" in prompt_lower else "pom.xml"
                return f"""# Implementation Plan (Claude Mocked)
1. [NEW] Create `{build_item}` with Spring Boot dependencies.
2. [NEW] Create `src/main/java/com/example/demo/DemoApplication.java` with Spring Boot REST controller.
3. Verify connection.
"""
            elif is_spring_framework:
                build_item = "build.gradle" if "gradle" in prompt_lower else "pom.xml"
                return f"""# Implementation Plan (Claude Mocked)
1. [NEW] Create `{build_item}` with Spring Framework dependencies (spring-context).
2. [NEW] Create `src/main/java/com/example/demo/AppConfig.java` with Spring @Configuration.
3. Verify connection.
"""
            elif is_plain_java:
                return """# Implementation Plan (Claude Mocked)
1. [NEW] Create `src/main/java/com/example/Main.java` with application logic.
2. Run sanity check.
"""
            return """# Implementation Plan (Claude Mocked)
1. [NEW] Create `output_claude.py` with advanced network utility logic.
2. Verify connection.
"""
