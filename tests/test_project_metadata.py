import tomllib
from pathlib import Path


def test_project_pins_uv_python_to_stable_312():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    python_version = Path(".python-version").read_text(encoding="utf-8").strip()

    assert python_version == "3.12.7"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.13"


def test_project_declares_build_backend_for_uv_console_script():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["build-system"]["requires"] == ["setuptools>=69"]
    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"
