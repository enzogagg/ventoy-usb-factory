# Task 6 Report

Files changed:
- `src/ventoy_usb_factory/jobs.py`
- `tests/test_jobs.py`
- `.superpowers/sdd/2026-08-19-ventoy-usb-factory/task-6-report.md`

Tests:
- `pytest tests/test_jobs.py -v`: 4 passed
- `pytest -v`: 28 passed
- `PATH=".venv/bin:$PATH" ruff check .`: passed

Commit hash: 1ab0dc4

Concerns:
- None.

## Review Fix

Files changed:
- `src/ventoy_usb_factory/jobs.py`
- `tests/test_jobs.py`
- `.superpowers/sdd/2026-08-19-ventoy-usb-factory/task-6-report.md`

Fix:
- Per-drive worker wrapper now catches all exceptions so non-`RuntimeError` failures are isolated to the failing drive.
- Added regression coverage for a `ValueError` on one drive while another drive completes.

Tests:
- `pytest tests/test_jobs.py -v`: 5 passed
- `pytest -v`: 29 passed
- `PATH=".venv/bin:$PATH" ruff check .`: passed

Commit hash: pending until fix commit is created

Concerns:
- None.
