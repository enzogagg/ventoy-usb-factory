from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    iso_dir: Path
    log_dir: Path
    ventoy_installer: Path
    max_concurrent_jobs: int


def _defaults(base_dir: Path) -> dict[str, Any]:
    return {
        "host": "127.0.0.1",
        "port": 8080,
        "iso_dir": base_dir / "isos",
        "log_dir": base_dir / "logs",
        "ventoy_installer": base_dir / "ventoy" / "Ventoy2Disk.sh",
        "max_concurrent_jobs": 2,
    }


def load_config(path: Path | None = None) -> AppConfig:
    values = _defaults(Path.cwd())
    if path is not None and path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        values.update(loaded)

    return AppConfig(
        host=str(values["host"]),
        port=int(values["port"]),
        iso_dir=Path(values["iso_dir"]),
        log_dir=Path(values["log_dir"]),
        ventoy_installer=Path(values["ventoy_installer"]),
        max_concurrent_jobs=max(1, int(values["max_concurrent_jobs"])),
    )


def ensure_runtime_dirs(config: AppConfig) -> None:
    config.iso_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
