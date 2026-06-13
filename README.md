# Multi-Agent Coding Assistant (MACA)

> [!WARNING]
> **MACA is currently in active development and is in the ALPHA stage.**
> You may encounter bugs, breaking changes, or unfinished features.

MACA is a **local-first, hybrid AI coding assistant** that routes work by complexity and coordinates planning, coding, and review agents directly in your workspace.

> **Why it matters:** simple tasks stay on your machine, while more demanding work can use powerful cloud models only when they are truly needed.

## ✨ What Makes MACA Different

- **Local-first by design:** keep routine work private, fast, and free from token billing.
- **Hybrid routing:** use local models for simple tasks and stronger cloud models for harder reasoning.
- **Agentic workflow:** planner, coder, and reviewer agents collaborate to improve the final result.

## 🚀 Core Features

- **Smart task routing:** analyzes each request and sends it to the best backend for the job.
  - **Simple tasks:** local Gemma (`gemma2:2b`) via Ollama.
  - **Medium complexity tasks:** Google Gemini (`gemini-3.5-flash`) via REST API. If Gemini is offline/unconfigured, falls back to Anthropic Claude, then local Gemma.
  - **Complex / Very Complex tasks:** Anthropic Claude (default `claude-opus-4-8` or custom model) via Messages API. If Claude is offline/unconfigured, falls back to Google Gemini, then local Gemma.
- **Multi-agent orchestration:** coordinates a planner, coder, and reviewer to work through tasks in sequence.
  - **Planner Agent:** inspects the codebase and creates an implementation plan.
  - **Coder Agent:** writes and applies the actual code changes.
  - **Reviewer Agent:** checks for logic, syntax, and safety issues before final approval.
- **Auto-apply workflow:** updates your files directly in the current workspace.
- **Robust fallbacks:** handles blocked Ollama ports, offline/mock mode, and terminal output fallback paths without breaking the experience.

---

## 🏗️ Architecture

```mermaid
graph TD
    User([User Prompt]) --> Router[Task Router]
    Router -.->|1. Classify Task| Gemma[Local Gemma Client]
    Gemma -.->|2. Complexity Result| Router

    Router -->|SIMPLE| Gemma
    Router -->|MEDIUM| Decider1{Backend Availability}
    Router -->|COMPLEX / VERY_COMPLEX| Decider2{Backend Availability}

    Decider1 -->|Gemini Available| Gemini[Gemini Client]
    Decider1 -->|Fallback| Claude[Claude Client]
    Decider1 -->|None Available| Gemma

    Decider2 -->|Claude Available| Claude
    Decider2 -->|Fallback| Gemini
    Decider2 -->|None Available| Gemma

    Gemma & Gemini & Claude --> Orchestrator[Multi-Agent Orchestrator]

    subgraph Agents
        Orchestrator --> Planner[Planner Agent]
        Planner --> Coder[Coder Agent]
        Coder --> Reviewer[Reviewer Agent]
    end

    Reviewer --> Write[File System Writer]
    Write --> Workspace[(Workspace)]
```

> **Note on Complexity Classification**: The Task Router queries the local Gemma model (`gemma2:2b`) to classify prompt complexity. If Gemma is offline, it falls back to a regex-based keyword density and word count heuristic classifier.

---

## 🛠️ Setup Instructions

### 1. Install and run the CLI
Use the local launcher scripts under [local/scripts](local/scripts):
```sh
./local/scripts/install_mac.sh
./local/scripts/run_mac.sh
```

If you only need the Gemma/Ollama setup, use:
```sh
./local/scripts/setup_gemma.sh
```

### 2. Configure API Keys (Environment or macOS Keychain)
MACA uses Google Gemini and Anthropic Claude for medium and above tasks. For secure setup details, see [docs/keys_setup.md](docs/keys_setup.md).

* **Quick Env Setup**:
  ```bash
  export GEMINI_API_KEY="your-gemini-api-key"
  export CLAUDE_API_KEY="your-claude-api-key"
  ```

  You can optionally customize the models and request timeouts (in seconds):
  ```bash
  export GEMINI_MODEL="gemini-3.5-flash"
  export GEMINI_TIMEOUT_SECONDS="120"

  export CLAUDE_MODEL="claude-opus-4-8"
  export CLAUDE_TIMEOUT_SECONDS="120"
  ```
* **Recommended macOS Keychain + .zshenv Setup**:
  ```bash
  security add-generic-password -a "$USER" -s "MACA_GEMINI_API_KEY" -w "your-gemini-key"
  echo 'export GEMINI_API_KEY="$(security find-generic-password -a "$USER" -s "MACA_GEMINI_API_KEY" -w 2>/dev/null)"' >> ~/.zshenv
  source ~/.zshenv
  ```
  This keeps the secret in your Keychain and makes it available to MACA every time a new zsh session starts.

### 3. Run tests
```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

---

## 💻 How to Use

### Run in Interactive REPL Mode
Launch the interactive console:
```sh
python3 -B src/maca/main.py
```

### Run a Single Command Task
Submit a task directly from your terminal:
```sh
maca "write a simple hello world script in output.py"
```

### Force a Specific Model
Override default task routing:
```sh
maca --model gemini "implement a custom tokenizer"
maca --model claude "implement a custom tokenizer"
```

### Run in Mock Mode (Simulated Run)
Test the orchestrator workflow without local models or API keys:
```sh
maca --mock "create an event logging class in python"
```
