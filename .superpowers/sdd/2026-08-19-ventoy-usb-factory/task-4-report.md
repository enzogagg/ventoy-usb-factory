# Task 4 Report

Files changed:
- `src/ventoy_usb_factory/isos.py`
- `tests/test_isos.py`
- `.superpowers/sdd/2026-08-19-ventoy-usb-factory/task-4-report.md`

Tests:
- `pytest tests/test_isos.py -v`: 3 passed
- `pytest -v`: 12 passed
- `PATH=".venv/bin:$PATH" ruff check .`: all checks passed

Commit hash: pending

Concerns:
- `ruff` is not available on the default PATH; verification used `.venv/bin` as requested.
- Pre-existing untracked `docs/`, egg-info, and `__pycache__` paths were left untouched.
