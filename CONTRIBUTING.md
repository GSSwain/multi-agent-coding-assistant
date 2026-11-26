# Contributing to MACA

Thanks for your interest in contributing to this project.

## Ways to contribute
- Report bugs and suggest improvements through issues.
- Improve tests, docs, or CLI behavior.
- Submit pull requests with focused changes.

## Development setup
1. Clone the repository.
2. Create and activate a virtual environment.
3. Install the package in editable mode:
   ```sh
   python -m pip install --upgrade pip setuptools wheel
   python -m pip install hatchling
   python -m pip install -e .
   ```
4. Run tests:
   - **Linux / Unix**:
     ```sh
     PYTHONPATH=src python -m unittest discover -s tests -v
     ```
   - **Windows (PowerShell)**:
     ```powershell
     $env:PYTHONPATH="src"; python -m unittest discover -s tests -v
     ```

## Pull request expectations
- Keep changes small and reviewable.
- Include tests for behavior changes when possible.
- **ALWAYS keep documentation updated**: Any changes affecting architecture, agents, stages, model routing, CLI flags, configuration, or file outputs must be reflected in `README.md` and `docs/architecture.md`.
- Ensure the full validation suite passes:
  - **Linux / Unix**:
    ```sh
    PYTHONPATH=src python -m unittest discover -s tests -v && ruff check . && ruff format --check . && mypy src && bandit -c pyproject.toml -r src/
    ```
  - **Windows (PowerShell)**:
    ```powershell
    $env:PYTHONPATH="src"
    python -m unittest discover -s tests -v
    ruff check .
    ruff format --check .
    mypy src
    bandit -c pyproject.toml -r src/
    ```
    *(In PowerShell 7+, you can chain these with `&&`: `$env:PYTHONPATH="src"; python -m unittest discover -s tests -v && ruff check . && ruff format --check . && mypy src && bandit -c pyproject.toml -r src/`.)*
