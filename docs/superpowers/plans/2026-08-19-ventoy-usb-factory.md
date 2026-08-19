# Ventoy USB Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Ubuntu-first web tool that safely installs Ventoy on multiple selected USB drives and copies Windows 10, Windows 11, and Ubuntu ISO files.

**Architecture:** Implement a Python FastAPI backend with server-rendered HTML and minimal JavaScript. Keep hardware access behind explicit service interfaces so unit tests use fake command runners and no destructive command runs unless a job explicitly reaches the worker layer.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Jinja2, PyYAML, pytest, httpx, Ruff, standard-library subprocess/pathlib/dataclasses/asyncio.

**Spec:** `docs/superpowers/specs/2026-08-19-ventoy-usb-factory-design.md`

## Global Constraints

- First supported platform is Ubuntu; direct disk writing on macOS and Windows is not part of MVP.
- Web UI binds only to `127.0.0.1` by default.
- Backend may require `sudo` because Ventoy installation and partition handling need raw block-device access.
- Docker is not the primary runtime.
- Never auto-select drives.
- Require explicit confirmation for each selected drive before installation.
- Re-scan devices immediately before each destructive operation.
- Refuse to operate if device identity changed, disappeared, or became mounted as a system path.
- Avoid shell string interpolation for device paths; spawn commands with argument arrays.
- Local ISO files are preferred; development ISO directory is `./isos`.
- Ubuntu download target is latest LTS desktop ISO from official Ubuntu release URLs.
- Windows ISO automatic resolution must use official Microsoft URLs when stable links are available; otherwise show manual fallback.
- Default max concurrent drive jobs is two.
- Active job state can be in memory; logs are written under `./logs` during development.

---

## File Structure

- `pyproject.toml`: package metadata, dependencies, test/lint config, console script.
- `README.md`: local setup, safety warning, run commands, Ventoy/ISO setup.
- `config.example.yaml`: documented development config.
- `src/ventoy_usb_factory/__init__.py`: package marker.
- `src/ventoy_usb_factory/config.py`: load and validate app config.
- `src/ventoy_usb_factory/models.py`: dataclasses/enums shared by services and API.
- `src/ventoy_usb_factory/commands.py`: safe command runner interface and subprocess implementation.
- `src/ventoy_usb_factory/devices.py`: Linux USB discovery and safety classification.
- `src/ventoy_usb_factory/isos.py`: local ISO scan and official-source download planning.
- `src/ventoy_usb_factory/jobs.py`: in-memory job store, job validation, concurrent orchestration.
- `src/ventoy_usb_factory/workers.py`: per-drive Ventoy install/copy workflow.
- `src/ventoy_usb_factory/app.py`: FastAPI app, JSON endpoints, HTML routes, SSE endpoint.
- `src/ventoy_usb_factory/templates/base.html`: shared page shell.
- `src/ventoy_usb_factory/templates/dashboard.html`: device/ISO/job dashboard.
- `src/ventoy_usb_factory/static/app.js`: polling, selection, confirmation, job submission, SSE updates.
- `src/ventoy_usb_factory/static/styles.css`: safety-oriented responsive styling.
- `tests/conftest.py`: shared fixtures.
- `tests/test_config.py`: config loading tests.
- `tests/test_devices.py`: `lsblk` parsing and safety classification tests.
- `tests/test_isos.py`: ISO scanner/downloader-state tests.
- `tests/test_jobs.py`: job validation and orchestration tests.
- `tests/test_app.py`: API endpoint tests.

---

### Task 1: Project Scaffold And Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `config.example.yaml`
- Create: `src/ventoy_usb_factory/__init__.py`
- Create: `src/ventoy_usb_factory/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `AppConfig` dataclass with fields `host: str`, `port: int`, `iso_dir: Path`, `log_dir: Path`, `ventoy_installer: Path`, `max_concurrent_jobs: int`.
- Produces: `load_config(path: Path | None = None) -> AppConfig`.
- Produces: `ensure_runtime_dirs(config: AppConfig) -> None`.

- [ ] **Step 1: Write the failing config tests**

```python
from pathlib import Path

from ventoy_usb_factory.config import load_config


def test_load_config_uses_safe_development_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    config = load_config(None)

    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.iso_dir == tmp_path / "isos"
    assert config.log_dir == tmp_path / "logs"
    assert config.ventoy_installer == tmp_path / "ventoy" / "Ventoy2Disk.sh"
    assert config.max_concurrent_jobs == 2


def test_load_config_reads_yaml_values(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "host: 127.0.0.1\n"
        "port: 9090\n"
        "iso_dir: /tmp/custom-isos\n"
        "log_dir: /tmp/custom-logs\n"
        "ventoy_installer: /opt/ventoy/Ventoy2Disk.sh\n"
        "max_concurrent_jobs: 1\n",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.port == 9090
    assert config.iso_dir == Path("/tmp/custom-isos")
    assert config.log_dir == Path("/tmp/custom-logs")
    assert config.ventoy_installer == Path("/opt/ventoy/Ventoy2Disk.sh")
    assert config.max_concurrent_jobs == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`

Expected: FAIL because `ventoy_usb_factory.config` does not exist.

- [ ] **Step 3: Create package metadata**

```toml
[project]
name = "ventoy-usb-factory"
version = "0.1.0"
description = "Local Ubuntu-first Ventoy USB preparation tool"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "jinja2>=3.1",
  "pyyaml>=6.0",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "httpx>=0.27",
  "ruff>=0.6",
]

[project.scripts]
ventoy-usb-factory = "ventoy_usb_factory.app:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 4: Implement config loading**

```python
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
    base_dir = Path.cwd()
    values = _defaults(base_dir)
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
```

- [ ] **Step 5: Add README and example config**

```yaml
host: 127.0.0.1
port: 8080
iso_dir: ./isos
log_dir: ./logs
ventoy_installer: ./ventoy/Ventoy2Disk.sh
max_concurrent_jobs: 2
```

README must include this warning exactly: `WARNING: Installing Ventoy erases the selected USB drive. Verify the device path, model, and size before confirming.`

- [ ] **Step 6: Run tests and lint**

Run: `pytest tests/test_config.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git init
git add pyproject.toml README.md config.example.yaml src tests
git commit -m "chore: scaffold ventoy usb factory"
```

---

### Task 2: Shared Models And Safe Command Runner

**Files:**
- Create: `src/ventoy_usb_factory/models.py`
- Create: `src/ventoy_usb_factory/commands.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: `CommandResult(args: list[str], returncode: int, stdout: str, stderr: str)`.
- Produces: `CommandRunner.run(args: list[str], timeout: int | None = None) -> CommandResult` protocol.
- Produces: `SubprocessCommandRunner` implementation that uses `subprocess.run(args, shell=False, text=True, capture_output=True)`.
- Produces: enums `SafetyStatus`, `IsoStatus`, `JobStatus`, `JobStage`.
- Produces: dataclasses `BlockPartition`, `UsbDevice`, `IsoEntry`, `JobEvent`, `DriveJob`, `PreparationJob`.

- [ ] **Step 1: Write model and command tests in `tests/conftest.py`**

```python
import pytest

from ventoy_usb_factory.commands import CommandResult


class FakeCommandRunner:
    def __init__(self, results: list[CommandResult]):
        self.results = list(results)
        self.calls: list[list[str]] = []

    def run(self, args: list[str], timeout: int | None = None) -> CommandResult:
        self.calls.append(args)
        if not self.results:
            raise AssertionError(f"No fake result configured for {args}")
        return self.results.pop(0)


@pytest.fixture
def command_result():
    def factory(args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0):
        return CommandResult(args=args, stdout=stdout, stderr=stderr, returncode=returncode)

    return factory
```

- [ ] **Step 2: Implement shared models**

```python
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import time


class SafetyStatus(StrEnum):
    ELIGIBLE = "eligible"
    UNSAFE_SYSTEM_DISK = "unsafe_system_disk"
    NOT_REMOVABLE = "not_removable"
    UNKNOWN = "unknown"


class IsoStatus(StrEnum):
    READY = "ready"
    MISSING = "missing"
    DOWNLOAD_AVAILABLE = "download_available"
    MANUAL_REQUIRED = "manual_required"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStage(StrEnum):
    QUEUED = "queued"
    REVALIDATING = "revalidating"
    UNMOUNTING = "unmounting"
    INSTALLING_VENTOY = "installing_ventoy"
    WAITING_FOR_PARTITIONS = "waiting_for_partitions"
    MOUNTING = "mounting"
    COPYING_ISOS = "copying_isos"
    SYNCING = "syncing"
    UNMOUNTING_FINAL = "unmounting_final"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class BlockPartition:
    name: str
    path: Path
    mountpoints: list[Path]
    fstype: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class UsbDevice:
    path: Path
    name: str
    model: str | None
    vendor: str | None
    serial: str | None
    size_bytes: int
    removable: bool
    transport: str | None
    partitions: list[BlockPartition]
    safety: SafetyStatus
    safety_reason: str


@dataclass(frozen=True)
class IsoEntry:
    key: str
    name: str
    status: IsoStatus
    path: Path | None
    size_bytes: int | None
    version: str | None
    message: str


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    device_path: str
    stage: JobStage
    message: str
    created_at: float = field(default_factory=time)


@dataclass
class DriveJob:
    device: UsbDevice
    status: JobStatus = JobStatus.PENDING
    stage: JobStage = JobStage.QUEUED
    error: str | None = None


@dataclass
class PreparationJob:
    id: str
    drives: list[DriveJob]
    iso_keys: list[str]
    status: JobStatus = JobStatus.PENDING
    events: list[JobEvent] = field(default_factory=list)
```

- [ ] **Step 3: Implement command runner**

```python
import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: list[str], timeout: int | None = None) -> CommandResult:
        raise NotImplementedError


class SubprocessCommandRunner:
    def run(self, args: list[str], timeout: int | None = None) -> CommandResult:
        completed = subprocess.run(
            args,
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
```

- [ ] **Step 4: Run tests and lint**

Run: `pytest -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ventoy_usb_factory/models.py src/ventoy_usb_factory/commands.py tests/conftest.py
git commit -m "feat: add shared models and command runner"
```

---

### Task 3: Linux USB Device Discovery And Safety Classification

**Files:**
- Create: `src/ventoy_usb_factory/devices.py`
- Create: `tests/test_devices.py`

**Interfaces:**
- Consumes: `CommandRunner`, `CommandResult`, `UsbDevice`, `BlockPartition`, `SafetyStatus`.
- Produces: `LinuxDeviceService(runner: CommandRunner)`.
- Produces: `LinuxDeviceService.list_devices() -> list[UsbDevice]`.
- Produces: `LinuxDeviceService.find_eligible_by_path(path: Path) -> UsbDevice | None`.

- [ ] **Step 1: Write failing parser and safety tests**

```python
from pathlib import Path

from conftest import FakeCommandRunner
from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.models import SafetyStatus


def test_list_devices_marks_usb_without_system_mountpoints_eligible(command_result):
    stdout = """
    {
      "blockdevices": [
        {"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[
          {"name":"sdb1","path":"/dev/sdb1","type":"part","mountpoints":["/media/user/OLD"],"fstype":"vfat","label":"OLD"}
        ]}
      ]
    }
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(["lsblk"], stdout=stdout)]))

    devices = service.list_devices()

    assert len(devices) == 1
    assert devices[0].path == Path("/dev/sdb")
    assert devices[0].safety == SafetyStatus.ELIGIBLE
    assert devices[0].partitions[0].mountpoints == [Path("/media/user/OLD")]


def test_list_devices_rejects_system_disk(command_result):
    stdout = """
    {"blockdevices":[{"name":"sda","path":"/dev/sda","type":"disk","rm":false,"tran":"sata","size":512000000000,"model":"SSD","vendor":"ATA","serial":"SYS","children":[
      {"name":"sda2","path":"/dev/sda2","type":"part","mountpoints":["/"],"fstype":"ext4","label":"root"}
    ]}]}
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(["lsblk"], stdout=stdout)]))

    devices = service.list_devices()

    assert devices[0].safety == SafetyStatus.UNSAFE_SYSTEM_DISK


def test_list_devices_rejects_non_removable_disk(command_result):
    stdout = """
    {"blockdevices":[{"name":"sdc","path":"/dev/sdc","type":"disk","rm":false,"tran":"sata","size":1000000000,"model":"Disk","vendor":"ATA","serial":"D1","children":[]}]}
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(["lsblk"], stdout=stdout)]))

    devices = service.list_devices()
    assert devices[0].safety == SafetyStatus.NOT_REMOVABLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_devices.py -v`

Expected: FAIL because `ventoy_usb_factory.devices` does not exist.

- [ ] **Step 3: Implement `LinuxDeviceService`**

```python
import json
from pathlib import Path

from ventoy_usb_factory.commands import CommandRunner
from ventoy_usb_factory.models import BlockPartition, SafetyStatus, UsbDevice

SYSTEM_MOUNTPOINTS = {Path("/"), Path("/boot"), Path("/home")}


class LinuxDeviceService:
    def __init__(self, runner: CommandRunner):
        self.runner = runner

    def list_devices(self) -> list[UsbDevice]:
        result = self.runner.run([
            "lsblk",
            "--json",
            "--bytes",
            "--output",
            "NAME,PATH,TYPE,RM,TRAN,SIZE,MODEL,VENDOR,SERIAL,MOUNTPOINTS,FSTYPE,LABEL",
        ])
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "lsblk failed")
        payload = json.loads(result.stdout)
        return [self._device_from_raw(raw) for raw in payload.get("blockdevices", []) if raw.get("type") == "disk"]

    def find_eligible_by_path(self, path: Path) -> UsbDevice | None:
        for device in self.list_devices():
            if device.path == path and device.safety == SafetyStatus.ELIGIBLE:
                return device
        return None

    def _device_from_raw(self, raw: dict) -> UsbDevice:
        partitions = [self._partition_from_raw(child) for child in raw.get("children") or []]
        safety, reason = self._classify(raw, partitions)
        return UsbDevice(
            path=Path(raw["path"]),
            name=str(raw["name"]),
            model=raw.get("model"),
            vendor=raw.get("vendor"),
            serial=raw.get("serial"),
            size_bytes=int(raw.get("size") or 0),
            removable=bool(raw.get("rm")),
            transport=raw.get("tran"),
            partitions=partitions,
            safety=safety,
            safety_reason=reason,
        )

    def _partition_from_raw(self, raw: dict) -> BlockPartition:
        mountpoints = [Path(m) for m in raw.get("mountpoints") or [] if m]
        return BlockPartition(
            name=str(raw["name"]),
            path=Path(raw["path"]),
            mountpoints=mountpoints,
            fstype=raw.get("fstype"),
            label=raw.get("label"),
        )

    def _classify(self, raw: dict, partitions: list[BlockPartition]) -> tuple[SafetyStatus, str]:
        mountpoints = {mount for partition in partitions for mount in partition.mountpoints}
        if mountpoints & SYSTEM_MOUNTPOINTS:
            return SafetyStatus.UNSAFE_SYSTEM_DISK, "contains a system mountpoint"
        if not bool(raw.get("rm")) and raw.get("tran") != "usb":
            return SafetyStatus.NOT_REMOVABLE, "device is not removable USB storage"
        return SafetyStatus.ELIGIBLE, "eligible removable USB storage"
```

- [ ] **Step 4: Run tests and lint**

Run: `pytest tests/test_devices.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ventoy_usb_factory/devices.py tests/test_devices.py
git commit -m "feat: detect eligible linux usb devices"
```

---

### Task 4: ISO Inventory And Hybrid Source Status

**Files:**
- Create: `src/ventoy_usb_factory/isos.py`
- Create: `tests/test_isos.py`

**Interfaces:**
- Consumes: `AppConfig`, `IsoEntry`, `IsoStatus`.
- Produces: `IsoService(config: AppConfig)`.
- Produces: `IsoService.list_isos() -> list[IsoEntry]`.
- Produces: `IsoService.ready_iso_paths(keys: list[str]) -> list[Path]`.

- [ ] **Step 1: Write failing ISO tests**

```python
from pathlib import Path

from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.isos import IsoService
from ventoy_usb_factory.models import IsoStatus


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        host="127.0.0.1",
        port=8080,
        iso_dir=tmp_path,
        log_dir=tmp_path / "logs",
        ventoy_installer=tmp_path / "ventoy" / "Ventoy2Disk.sh",
        max_concurrent_jobs=2,
    )


def test_list_isos_prefers_local_windows_and_ubuntu_files(tmp_path):
    (tmp_path / "Win10_22H2.iso").write_bytes(b"win10")
    (tmp_path / "Win11_24H2.iso").write_bytes(b"win11")
    (tmp_path / "ubuntu-24.04.3-desktop-amd64.iso").write_bytes(b"ubuntu")

    entries = IsoService(make_config(tmp_path)).list_isos()

    assert {entry.key: entry.status for entry in entries} == {
        "windows10": IsoStatus.READY,
        "windows11": IsoStatus.READY,
        "ubuntu": IsoStatus.READY,
    }


def test_list_isos_marks_windows_manual_when_missing(tmp_path):
    entries = IsoService(make_config(tmp_path)).list_isos()
    by_key = {entry.key: entry for entry in entries}

    assert by_key["windows10"].status == IsoStatus.MANUAL_REQUIRED
    assert "Microsoft" in by_key["windows10"].message
    assert by_key["windows11"].status == IsoStatus.MANUAL_REQUIRED


def test_ready_iso_paths_only_returns_ready_requested_files(tmp_path):
    (tmp_path / "ubuntu-24.04.3-desktop-amd64.iso").write_bytes(b"ubuntu")

    paths = IsoService(make_config(tmp_path)).ready_iso_paths(["ubuntu", "windows11"])

    assert paths == [tmp_path / "ubuntu-24.04.3-desktop-amd64.iso"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_isos.py -v`

Expected: FAIL because `ventoy_usb_factory.isos` does not exist.

- [ ] **Step 3: Implement ISO scanning**

```python
from pathlib import Path

from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.models import IsoEntry, IsoStatus

REQUIRED_ISOS = {
    "windows10": ("Windows 10", ("win10", "windows10")),
    "windows11": ("Windows 11", ("win11", "windows11")),
    "ubuntu": ("Ubuntu LTS", ("ubuntu", "desktop", "amd64")),
}


class IsoService:
    def __init__(self, config: AppConfig):
        self.config = config

    def list_isos(self) -> list[IsoEntry]:
        self.config.iso_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self.config.iso_dir.glob("*.iso"))
        return [self._entry_for(key, name, tokens, files) for key, (name, tokens) in REQUIRED_ISOS.items()]

    def ready_iso_paths(self, keys: list[str]) -> list[Path]:
        requested = set(keys)
        return [entry.path for entry in self.list_isos() if entry.key in requested and entry.path is not None and entry.status == IsoStatus.READY]

    def _entry_for(self, key: str, name: str, tokens: tuple[str, ...], files: list[Path]) -> IsoEntry:
        match = self._find_local(tokens, files)
        if match is not None:
            return IsoEntry(
                key=key,
                name=name,
                status=IsoStatus.READY,
                path=match,
                size_bytes=match.stat().st_size,
                version=match.stem,
                message="Local ISO ready",
            )
        if key == "ubuntu":
            return IsoEntry(key, name, IsoStatus.DOWNLOAD_AVAILABLE, None, None, "latest-lts", "Official Ubuntu LTS download can be attempted")
        return IsoEntry(key, name, IsoStatus.MANUAL_REQUIRED, None, None, None, "Download this ISO from Microsoft and place it in the ISO folder")

    def _find_local(self, tokens: tuple[str, ...], files: list[Path]) -> Path | None:
        for file in files:
            lower = file.name.lower()
            if all(token in lower for token in tokens):
                return file
        return None
```

- [ ] **Step 4: Run tests and lint**

Run: `pytest tests/test_isos.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ventoy_usb_factory/isos.py tests/test_isos.py
git commit -m "feat: add hybrid iso inventory"
```

---

### Task 5: Per-Drive Worker Workflow With Fakeable Commands

**Files:**
- Create: `src/ventoy_usb_factory/workers.py`
- Create: `tests/test_workers.py`

**Interfaces:**
- Consumes: `AppConfig`, `CommandRunner`, `LinuxDeviceService`, `UsbDevice`, `IsoEntry`, `JobEvent`, `JobStage`.
- Produces: `DriveWorker(config: AppConfig, runner: CommandRunner, devices: LinuxDeviceService)`.
- Produces: `DriveWorker.prepare_drive(job_id: str, device: UsbDevice, iso_paths: list[Path], emit: Callable[[JobEvent], None]) -> None`.

- [ ] **Step 1: Write failing worker tests**

```python
from pathlib import Path

import pytest

from conftest import FakeCommandRunner
from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.models import BlockPartition, JobEvent, JobStage, SafetyStatus, UsbDevice
from ventoy_usb_factory.workers import DriveWorker


def config(tmp_path: Path) -> AppConfig:
    return AppConfig("127.0.0.1", 8080, tmp_path / "isos", tmp_path / "logs", tmp_path / "ventoy" / "Ventoy2Disk.sh", 2)


def eligible_device() -> UsbDevice:
    return UsbDevice(Path("/dev/sdb"), "sdb", "Flash", "USB", "ABC", 16000000000, True, "usb", [BlockPartition("sdb1", Path("/dev/sdb1"), [Path("/media/old")])], SafetyStatus.ELIGIBLE, "eligible")


def test_prepare_drive_uses_argument_arrays_and_emits_stages(tmp_path, command_result):
    lsblk_stdout = '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}'
    runner = FakeCommandRunner([
        command_result(["lsblk"], stdout=lsblk_stdout),
        command_result(["umount"]),
        command_result(["ventoy"]),
        command_result(["partprobe"]),
        command_result(["mount"]),
        command_result(["rsync"]),
        command_result(["sync"]),
        command_result(["umount"]),
    ])
    events: list[JobEvent] = []

    worker = DriveWorker(config(tmp_path), runner, LinuxDeviceService(runner))
    worker.prepare_drive("job-1", eligible_device(), [tmp_path / "ubuntu.iso"], events.append)

    assert [event.stage for event in events][0] == JobStage.REVALIDATING
    assert events[-1].stage == JobStage.COMPLETE
    assert all(isinstance(call, list) for call in runner.calls)
    assert ["sudo", str(config(tmp_path).ventoy_installer), "-I", "/dev/sdb"] in runner.calls


def test_prepare_drive_refuses_changed_or_missing_device(tmp_path, command_result):
    runner = FakeCommandRunner([command_result(["lsblk"], stdout='{"blockdevices":[]}')])
    events: list[JobEvent] = []
    worker = DriveWorker(config(tmp_path), runner, LinuxDeviceService(runner))

    with pytest.raises(RuntimeError, match="no longer eligible"):
        worker.prepare_drive("job-1", eligible_device(), [], events.append)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workers.py -v`

Expected: FAIL because `ventoy_usb_factory.workers` does not exist.

- [ ] **Step 3: Implement worker workflow**

```python
from collections.abc import Callable
from pathlib import Path

from ventoy_usb_factory.commands import CommandRunner
from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.models import JobEvent, JobStage, UsbDevice


class DriveWorker:
    def __init__(self, config: AppConfig, runner: CommandRunner, devices: LinuxDeviceService):
        self.config = config
        self.runner = runner
        self.devices = devices

    def prepare_drive(self, job_id: str, device: UsbDevice, iso_paths: list[Path], emit: Callable[[JobEvent], None]) -> None:
        self._emit(emit, job_id, device, JobStage.REVALIDATING, "Revalidating selected device")
        current = self.devices.find_eligible_by_path(device.path)
        if current is None or current.serial != device.serial or current.size_bytes != device.size_bytes:
            raise RuntimeError(f"Device {device.path} is no longer eligible or changed identity")

        self._emit(emit, job_id, device, JobStage.UNMOUNTING, "Unmounting existing partitions")
        for partition in device.partitions:
            if partition.mountpoints:
                self._run(["umount", str(partition.path)])

        self._emit(emit, job_id, device, JobStage.INSTALLING_VENTOY, "Installing Ventoy")
        self._run(["sudo", str(self.config.ventoy_installer), "-I", str(device.path)])

        self._emit(emit, job_id, device, JobStage.WAITING_FOR_PARTITIONS, "Refreshing partition table")
        self._run(["partprobe", str(device.path)])

        mount_dir = self.config.log_dir / "mnt" / device.name
        mount_dir.mkdir(parents=True, exist_ok=True)
        data_partition = Path(f"{device.path}1")

        self._emit(emit, job_id, device, JobStage.MOUNTING, "Mounting Ventoy data partition")
        self._run(["mount", str(data_partition), str(mount_dir)])

        self._emit(emit, job_id, device, JobStage.COPYING_ISOS, "Copying ISO files")
        for iso_path in iso_paths:
            self._run(["rsync", "-ah", "--progress", str(iso_path), str(mount_dir / iso_path.name)])

        self._emit(emit, job_id, device, JobStage.SYNCING, "Syncing filesystem buffers")
        self._run(["sync"])

        self._emit(emit, job_id, device, JobStage.UNMOUNTING_FINAL, "Unmounting Ventoy data partition")
        self._run(["umount", str(mount_dir)])
        self._emit(emit, job_id, device, JobStage.COMPLETE, "Drive complete")

    def _run(self, args: list[str]) -> None:
        result = self.runner.run(args)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"Command failed: {args}")

    def _emit(self, emit: Callable[[JobEvent], None], job_id: str, device: UsbDevice, stage: JobStage, message: str) -> None:
        emit(JobEvent(job_id=job_id, device_path=str(device.path), stage=stage, message=message))
```

- [ ] **Step 4: Run worker tests and lint**

Run: `pytest tests/test_workers.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ventoy_usb_factory/workers.py tests/test_workers.py
git commit -m "feat: add safe drive preparation worker"
```

---

### Task 6: In-Memory Job Store And Concurrent Orchestration

**Files:**
- Create: `src/ventoy_usb_factory/jobs.py`
- Create: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `UsbDevice`, `IsoService.ready_iso_paths`, `DriveWorker.prepare_drive`, `PreparationJob`, `DriveJob`, `JobStatus`, `JobStage`.
- Produces: `JobService(devices: LinuxDeviceService, isos: IsoService, worker: DriveWorker, max_concurrent_jobs: int)`.
- Produces: `JobService.create_job(device_paths: list[Path], iso_keys: list[str], confirmations: dict[str, str]) -> PreparationJob`.
- Produces: `JobService.get_job(job_id: str) -> PreparationJob | None`.
- Produces: `JobService.list_jobs() -> list[PreparationJob]`.
- Produces: `JobService.run_job(job_id: str) -> None`.

- [ ] **Step 1: Write failing job tests**

```python
from pathlib import Path

import pytest

from ventoy_usb_factory.jobs import JobService
from ventoy_usb_factory.models import JobStatus, SafetyStatus, UsbDevice


class FakeDevices:
    def __init__(self, devices):
        self.devices = devices

    def list_devices(self):
        return self.devices


class FakeIsos:
    def ready_iso_paths(self, keys):
        return [Path(f"/isos/{key}.iso") for key in keys]


class FakeWorker:
    def __init__(self):
        self.prepared = []

    def prepare_drive(self, job_id, device, iso_paths, emit):
        self.prepared.append((job_id, device.path, iso_paths))


def device(path: str, safety=SafetyStatus.ELIGIBLE):
    return UsbDevice(Path(path), Path(path).name, "Flash", "USB", path, 16000000000, True, "usb", [], safety, "reason")


def test_create_job_requires_exact_confirmation_text():
    service = JobService(FakeDevices([device("/dev/sdb")]), FakeIsos(), FakeWorker(), 2)

    with pytest.raises(ValueError, match="confirmation"):
        service.create_job([Path("/dev/sdb")], ["ubuntu"], {"/dev/sdb": "wrong"})


def test_create_job_rejects_unsafe_device():
    service = JobService(FakeDevices([device("/dev/sda", SafetyStatus.UNSAFE_SYSTEM_DISK)]), FakeIsos(), FakeWorker(), 2)

    with pytest.raises(ValueError, match="not eligible"):
        service.create_job([Path("/dev/sda")], ["ubuntu"], {"/dev/sda": "ERASE /dev/sda"})


def test_run_job_marks_success_and_calls_worker():
    worker = FakeWorker()
    service = JobService(FakeDevices([device("/dev/sdb")]), FakeIsos(), worker, 2)
    job = service.create_job([Path("/dev/sdb")], ["ubuntu"], {"/dev/sdb": "ERASE /dev/sdb"})

    service.run_job(job.id)

    assert service.get_job(job.id).status == JobStatus.COMPLETED
    assert worker.prepared[0][1] == Path("/dev/sdb")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jobs.py -v`

Expected: FAIL because `ventoy_usb_factory.jobs` does not exist.

- [ ] **Step 3: Implement job service**

```python
from pathlib import Path
from threading import Lock, Semaphore, Thread
from uuid import uuid4

from ventoy_usb_factory.models import DriveJob, JobEvent, JobStage, JobStatus, PreparationJob, SafetyStatus


class JobService:
    def __init__(self, devices, isos, worker, max_concurrent_jobs: int):
        self.devices = devices
        self.isos = isos
        self.worker = worker
        self.semaphore = Semaphore(max(1, max_concurrent_jobs))
        self.jobs: dict[str, PreparationJob] = {}
        self.lock = Lock()

    def create_job(self, device_paths: list[Path], iso_keys: list[str], confirmations: dict[str, str]) -> PreparationJob:
        available = {device.path: device for device in self.devices.list_devices()}
        drives: list[DriveJob] = []
        for path in device_paths:
            device = available.get(path)
            if device is None or device.safety != SafetyStatus.ELIGIBLE:
                raise ValueError(f"Device {path} is not eligible")
            expected = f"ERASE {path}"
            if confirmations.get(str(path)) != expected:
                raise ValueError(f"Missing confirmation for {path}; expected '{expected}'")
            drives.append(DriveJob(device=device))
        if not drives:
            raise ValueError("At least one eligible device is required")
        job = PreparationJob(id=str(uuid4()), drives=drives, iso_keys=iso_keys)
        with self.lock:
            self.jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> PreparationJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[PreparationJob]:
        return list(self.jobs.values())

    def run_job(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.RUNNING
        iso_paths = self.isos.ready_iso_paths(job.iso_keys)
        threads = [Thread(target=self._run_drive, args=(job, drive, iso_paths)) for drive in job.drives]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        job.status = JobStatus.FAILED if any(drive.status == JobStatus.FAILED for drive in job.drives) else JobStatus.COMPLETED

    def _run_drive(self, job: PreparationJob, drive: DriveJob, iso_paths: list[Path]) -> None:
        with self.semaphore:
            drive.status = JobStatus.RUNNING
            try:
                self.worker.prepare_drive(job.id, drive.device, iso_paths, lambda event: self._record(job, drive, event))
                drive.status = JobStatus.COMPLETED
                drive.stage = JobStage.COMPLETE
            except Exception as exc:
                drive.status = JobStatus.FAILED
                drive.stage = JobStage.FAILED
                drive.error = str(exc)
                self._record(job, drive, JobEvent(job.id, str(drive.device.path), JobStage.FAILED, str(exc)))

    def _record(self, job: PreparationJob, drive: DriveJob, event: JobEvent) -> None:
        with self.lock:
            drive.stage = event.stage
            job.events.append(event)
```

- [ ] **Step 4: Run job tests and lint**

Run: `pytest tests/test_jobs.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ventoy_usb_factory/jobs.py tests/test_jobs.py
git commit -m "feat: orchestrate confirmed usb preparation jobs"
```

---

### Task 7: FastAPI JSON API And Localhost Startup

**Files:**
- Create: `src/ventoy_usb_factory/app.py`
- Create: `tests/test_app.py`

**Interfaces:**
- Consumes: `load_config`, `SubprocessCommandRunner`, `LinuxDeviceService`, `IsoService`, `DriveWorker`, `JobService`.
- Produces: `create_app(config: AppConfig | None = None, runner: CommandRunner | None = None) -> FastAPI`.
- Produces endpoints `GET /api/devices`, `GET /api/isos`, `POST /api/isos/refresh`, `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/events`.
- Produces: `main() -> None` that runs Uvicorn on configured `127.0.0.1` host.

- [ ] **Step 1: Write failing API tests**

```python
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import FakeCommandRunner
from ventoy_usb_factory.app import create_app
from ventoy_usb_factory.config import AppConfig


def test_api_lists_devices(tmp_path, command_result):
    config = AppConfig("127.0.0.1", 8080, tmp_path / "isos", tmp_path / "logs", tmp_path / "ventoy" / "Ventoy2Disk.sh", 2)
    stdout = '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}'
    app = create_app(config, FakeCommandRunner([command_result(["lsblk"], stdout=stdout)]))

    response = TestClient(app).get("/api/devices")

    assert response.status_code == 200
    assert response.json()[0]["path"] == "/dev/sdb"
    assert response.json()[0]["safety"] == "eligible"


def test_api_lists_isos(tmp_path):
    config = AppConfig("127.0.0.1", 8080, tmp_path / "isos", tmp_path / "logs", tmp_path / "ventoy" / "Ventoy2Disk.sh", 2)
    app = create_app(config)

    response = TestClient(app).get("/api/isos")

    assert response.status_code == 200
    assert {entry["key"] for entry in response.json()} == {"windows10", "windows11", "ubuntu"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`

Expected: FAIL because `ventoy_usb_factory.app` does not exist.

- [ ] **Step 3: Implement FastAPI app**

```python
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from threading import Thread

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ventoy_usb_factory.commands import CommandRunner, SubprocessCommandRunner
from ventoy_usb_factory.config import AppConfig, ensure_runtime_dirs, load_config
from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.isos import IsoService
from ventoy_usb_factory.jobs import JobService
from ventoy_usb_factory.workers import DriveWorker


class CreateJobRequest(BaseModel):
    device_paths: list[str]
    iso_keys: list[str]
    confirmations: dict[str, str]


def encode(value):
    if is_dataclass(value):
        return encode(asdict(value))
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def create_app(config: AppConfig | None = None, runner: CommandRunner | None = None) -> FastAPI:
    config = config or load_config(None)
    ensure_runtime_dirs(config)
    runner = runner or SubprocessCommandRunner()
    device_service = LinuxDeviceService(runner)
    iso_service = IsoService(config)
    worker = DriveWorker(config, runner, device_service)
    job_service = JobService(device_service, iso_service, worker, config.max_concurrent_jobs)
    app = FastAPI(title="Ventoy USB Factory")

    @app.get("/api/devices")
    def api_devices():
        return encode(device_service.list_devices())

    @app.get("/api/isos")
    def api_isos():
        return encode(iso_service.list_isos())

    @app.post("/api/isos/refresh")
    def api_isos_refresh():
        return encode(iso_service.list_isos())

    @app.post("/api/jobs")
    def api_create_job(request: CreateJobRequest):
        try:
            job = job_service.create_job([Path(path) for path in request.device_paths], request.iso_keys, request.confirmations)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        Thread(target=job_service.run_job, args=(job.id,), daemon=True).start()
        return encode(job)

    @app.get("/api/jobs")
    def api_jobs():
        return encode(job_service.list_jobs())

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str):
        job = job_service.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return encode(job)

    @app.get("/api/jobs/{job_id}/events")
    def api_job_events(job_id: str):
        def stream():
            job = job_service.get_job(job_id)
            if job is None:
                yield "event: error\ndata: Job not found\n\n"
                return
            for event in job.events:
                yield f"data: {json.dumps(encode(event))}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def main() -> None:
    config = load_config(Path("config.yaml") if Path("config.yaml").exists() else None)
    uvicorn.run(create_app(config), host=config.host, port=config.port)
```

- [ ] **Step 4: Run API tests and lint**

Run: `pytest tests/test_app.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ventoy_usb_factory/app.py tests/test_app.py
git commit -m "feat: expose local management api"
```

---

### Task 8: Server-Rendered Dashboard UI

**Files:**
- Modify: `src/ventoy_usb_factory/app.py`
- Create: `src/ventoy_usb_factory/templates/base.html`
- Create: `src/ventoy_usb_factory/templates/dashboard.html`
- Create: `src/ventoy_usb_factory/static/app.js`
- Create: `src/ventoy_usb_factory/static/styles.css`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: existing FastAPI service wiring.
- Produces route `GET /` that renders dashboard.
- Produces static mount `/static`.

- [ ] **Step 1: Add failing dashboard test**

```python
def test_dashboard_renders_safety_warning(tmp_path):
    config = AppConfig("127.0.0.1", 8080, tmp_path / "isos", tmp_path / "logs", tmp_path / "ventoy" / "Ventoy2Disk.sh", 2)
    response = TestClient(create_app(config)).get("/")

    assert response.status_code == 200
    assert "Ventoy USB Factory" in response.text
    assert "erases the selected USB drive" in response.text
```

- [ ] **Step 2: Run dashboard test to verify it fails**

Run: `pytest tests/test_app.py::test_dashboard_renders_safety_warning -v`

Expected: FAIL with 404 or missing text.

- [ ] **Step 3: Add templates and static files**

`base.html` must contain:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ventoy USB Factory</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main>{% block content %}{% endblock %}</main>
  <script src="/static/app.js"></script>
</body>
</html>
```

`dashboard.html` must contain sections with ids `devices`, `isos`, `jobs`, and confirmation text instructions using `ERASE /dev/sdb` as the concrete example.

```html
{% extends "base.html" %}
{% block content %}
<h1>Ventoy USB Factory</h1>
<p class="danger">WARNING: Installing Ventoy erases the selected USB drive. Verify the device path, model, and size before confirming.</p>
<section id="isos"><h2>ISO readiness</h2><div data-isos></div></section>
<section id="devices"><h2>USB drives</h2><div data-devices></div></section>
<section id="confirm"><h2>Confirm</h2><p>Type the exact confirmation string shown for each selected drive, for example <code>ERASE /dev/sdb</code>.</p><div data-confirmations></div><button data-start>Start preparation</button></section>
<section id="jobs"><h2>Jobs</h2><div data-jobs></div></section>
{% endblock %}
```

`styles.css` must make `.danger` visually prominent and keep cards readable under 800px width.

`app.js` must fetch `/api/devices`, `/api/isos`, `/api/jobs`, render cards, collect selected eligible devices, require confirmation strings, and submit `POST /api/jobs`.

- [ ] **Step 4: Mount templates/static in `app.py`**

```python
from pathlib import Path

from fastapi import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

# add this inside create_app immediately after app = FastAPI(title="Ventoy USB Factory")
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
```

- [ ] **Step 5: Run UI/API tests and lint**

Run: `pytest tests/test_app.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ventoy_usb_factory/app.py src/ventoy_usb_factory/templates src/ventoy_usb_factory/static tests/test_app.py
git commit -m "feat: add local web dashboard"
```

---

### Task 9: Documentation, Dry-Run Verification, And Manual Test Checklist

**Files:**
- Modify: `README.md`
- Create: `docs/manual-test-checklist.md`
- Create: `.gitignore`

**Interfaces:**
- Consumes: completed app and config.
- Produces: documented run commands and manual destructive-test gates.

- [ ] **Step 1: Add documentation content**

README must include:

```markdown
## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp config.example.yaml config.yaml
ventoy-usb-factory
```

## Ventoy Setup

Download the official Ventoy Linux release from https://www.ventoy.net/ and extract it to `./ventoy` so `./ventoy/Ventoy2Disk.sh` exists.

## ISO Folder

Place local ISO files in `./isos`. File names should include `Win10`, `Win11`, or `ubuntu` so the scanner can classify them.

## Safety

This tool is destructive. It never auto-selects USB drives. Each selected drive requires the exact confirmation string shown in the UI.
```

`.gitignore` must contain:

```gitignore
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
config.yaml
isos/
logs/
ventoy/
```

`docs/manual-test-checklist.md` must include the manual hardware cases from the spec and state that destructive tests require explicit tester consent.

- [ ] **Step 2: Run full verification**

Run: `pytest -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 3: Start app locally for smoke test**

Run: `ventoy-usb-factory`

Expected: Uvicorn starts on `http://127.0.0.1:8080` without binding to external interfaces.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/manual-test-checklist.md .gitignore
git commit -m "docs: add setup and hardware test checklist"
```

---

## Final Verification

- [ ] Run `pytest -v` and confirm all tests pass.
- [ ] Run `ruff check .` and confirm lint passes.
- [ ] Run `ventoy-usb-factory` and confirm the app binds to `127.0.0.1:8080`.
- [ ] Open `http://127.0.0.1:8080` and confirm the dashboard displays the destructive-operation warning.
- [ ] If hardware testing is approved, run the manual checklist with a disposable USB drive only.

## Spec Coverage Review

- Local Ubuntu-first web tool: Tasks 1, 7, and 8.
- Device list with safety classification: Task 3.
- Explicit per-drive confirmations: Tasks 6 and 8.
- Ventoy install and ISO copy flow: Task 5.
- Parallel jobs with default concurrency two: Task 6.
- Hybrid ISO local/manual/download status: Task 4.
- Localhost binding: Tasks 1, 7, and 9.
- Logs/config/ISO development paths: Tasks 1 and 9.
- Test coverage and manual hardware checklist: Tasks 3 through 9.
