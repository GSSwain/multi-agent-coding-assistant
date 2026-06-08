# AGENTS.md

## Repository guidance
- Prefer small, reviewable changes.
- Keep tests passing before submitting changes.
- Preserve the existing CLI behavior unless explicitly asked to change it.
- Update documentation when user-facing behavior changes.

## Validation
Run:
```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```
