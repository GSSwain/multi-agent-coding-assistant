# AGENTS.md

> Developer guidelines and validation instructions for AI coding assistants working on this repository. For MACA's internal multi-agent architecture documentation, see [docs/architecture.md](docs/architecture.md).

## Repository guidance
- Prefer small, reviewable changes.
- Keep tests passing before submitting changes.
- Preserve the existing CLI behavior unless explicitly asked to change it.
- **ALWAYS keep documentation updated**: Whenever features, architecture, agent protocols, CLI behavior, directory structures, or configurations change, immediately update `README.md`, `docs/architecture.md`, and any relevant guides. Never allow documentation to drift from implementation.

## Documentation Maintenance Rules
Whenever you make changes to this repository:
1. **Sync Documentation in Real-Time**: Update `README.md`, `docs/architecture.md`, and other relevant docs as part of the same change.
2. **Architecture & Agents**: If an agent or stage is added, modified, or re-routed, update the Mermaid diagrams, agent responsibilities table, and stage descriptions in both `README.md` and `docs/architecture.md`.
3. **Directory Structures & Metadata**: Accurately document task metadata directories (e.g. `.maca/<task>/`) and file formats (`plan.md`, `spec.md`, `<agent>.todo`, `progress.md`, `task.json`).
4. **Validation Deliverable**: Documentation updates are mandatory criteria for passing review alongside code tests and audits.

## Validation
Before submitting changes, run the full validation suite:

### Linux / Unix
```sh
# 1. Run all unit tests
PYTHONPATH=src python -m unittest discover -s tests -v

# 2. Linting and formatting checks
ruff check .
ruff format --check .

# 3. Static type analysis
mypy src

# 4. Security vulnerability audit
bandit -c pyproject.toml -r src/

# 5. End-to-end CLI execution verification (targets ./output or outside directory)
printf "y\n" | PYTHONPATH=src python -m maca.main --repo ./output --mock "Create a simple greeting function in greet.py"
```

Single one-liner:
```sh
PYTHONPATH=src python -m unittest discover -s tests -v && ruff check . && ruff format --check . && mypy src && bandit -c pyproject.toml -r src/ && (printf "y\n" | PYTHONPATH=src python -m maca.main --repo ./output --mock "Create a simple greeting function in greet.py")
```

### Windows (PowerShell)
```powershell
# 1. Run all unit tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests -v

# 2. Linting and formatting checks
ruff check .
ruff format --check .

# 3. Static type analysis
mypy src

# 4. Security vulnerability audit
bandit -c pyproject.toml -r src/

# 5. End-to-end CLI execution verification (targets ./output or outside directory)
$env:PYTHONPATH="src"; "y" | python -m maca.main --repo ./output --mock "Create a simple greeting function in greet.py"
```

Single one-liner (PowerShell 7+):
```powershell
$env:PYTHONPATH="src"; python -m unittest discover -s tests -v && ruff check . && ruff format --check . && mypy src && bandit -c pyproject.toml -r src/ && ("y" | python -m maca.main --repo ./output --mock "Create a simple greeting function in greet.py")
```
