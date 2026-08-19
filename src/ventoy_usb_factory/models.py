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
