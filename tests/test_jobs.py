from pathlib import Path

import pytest

from ventoy_usb_factory.jobs import JobService
from ventoy_usb_factory.models import JobEvent, JobStage, JobStatus, SafetyStatus, UsbDevice


class FakeDeviceService:
    def __init__(self, devices: list[UsbDevice]):
        self.devices = devices

    def list_devices(self) -> list[UsbDevice]:
        return self.devices


class FakeIsoService:
    def __init__(self, iso_paths: list[Path]):
        self.iso_paths = iso_paths
        self.requested_keys: list[str] | None = None

    def ready_iso_paths(self, keys: list[str]) -> list[Path]:
        self.requested_keys = keys
        return self.iso_paths


class FakeWorker:
    def __init__(self, failures: set[Path] | None = None, value_failures: set[Path] | None = None):
        self.failures = failures or set()
        self.value_failures = value_failures or set()
        self.calls: list[tuple[str, Path, list[Path]]] = []

    def prepare_drive(
        self,
        job_id: str,
        device: UsbDevice,
        iso_paths: list[Path],
        emit,
    ) -> None:
        self.calls.append((job_id, device.path, iso_paths))
        if device.path in self.value_failures:
            raise ValueError(f"invalid {device.path}")
        if device.path in self.failures:
            raise RuntimeError(f"failed {device.path}")
        emit(JobEvent(job_id, str(device.path), JobStage.COMPLETE, "complete"))


def device(path: str, safety: SafetyStatus = SafetyStatus.ELIGIBLE) -> UsbDevice:
    name = Path(path).name
    return UsbDevice(
        path=Path(path),
        name=name,
        model="Flash",
        vendor="USB",
        serial=f"serial-{name}",
        size_bytes=16_000_000_000,
        removable=True,
        transport="usb",
        partitions=[],
        safety=safety,
        safety_reason=safety.value,
    )


def service(
    devices: list[UsbDevice],
    worker: FakeWorker | None = None,
    isos: FakeIsoService | None = None,
) -> JobService:
    return JobService(
        FakeDeviceService(devices),
        isos or FakeIsoService([Path("/isos/ubuntu.iso")]),
        worker or FakeWorker(),
        max_concurrent_jobs=2,
    )


def test_create_job_requires_popup_confirmation_per_device():
    job_service = service([device("/dev/sdb")])

    with pytest.raises(ValueError, match="confirmation"):
        job_service.create_job([Path("/dev/sdb")], ["ubuntu"], {"/dev/sdb": "ERASE /dev/sdb"})


def test_create_job_rejects_unsafe_device():
    job_service = service([device("/dev/sda", SafetyStatus.UNSAFE_SYSTEM_DISK)])

    with pytest.raises(ValueError, match="not eligible"):
        job_service.create_job([Path("/dev/sda")], ["ubuntu"], {"/dev/sda": "CONFIRMED"})


def test_create_job_rejects_duplicate_device_paths():
    job_service = service([device("/dev/sdb")])

    with pytest.raises(ValueError, match="Duplicate device"):
        job_service.create_job(
            [Path("/dev/sdb"), Path("/dev/sdb")],
            ["ubuntu"],
            {"/dev/sdb": "CONFIRMED"},
        )

    assert job_service.list_jobs() == []


def test_create_job_records_requested_concurrency_limit():
    job_service = service([device("/dev/sdb"), device("/dev/sdc"), device("/dev/sdd")])

    job = job_service.create_job(
        [Path("/dev/sdb"), Path("/dev/sdc"), Path("/dev/sdd")],
        ["ubuntu"],
        {"/dev/sdb": "CONFIRMED", "/dev/sdc": "CONFIRMED", "/dev/sdd": "CONFIRMED"},
        max_concurrent_drives=3,
    )

    assert job.max_concurrent_drives == 3


def test_create_job_clamps_requested_concurrency_to_selected_drive_count():
    job_service = service([device("/dev/sdb"), device("/dev/sdc")])

    job = job_service.create_job(
        [Path("/dev/sdb"), Path("/dev/sdc")],
        ["ubuntu"],
        {"/dev/sdb": "CONFIRMED", "/dev/sdc": "CONFIRMED"},
        max_concurrent_drives=99,
    )

    assert job.max_concurrent_drives == 2


def test_run_job_calls_worker_and_marks_job_completed():
    worker = FakeWorker()
    isos = FakeIsoService([Path("/isos/ubuntu.iso")])
    job_service = service([device("/dev/sdb")], worker=worker, isos=isos)
    job = job_service.create_job([Path("/dev/sdb")], ["ubuntu"], {"/dev/sdb": "CONFIRMED"})

    job_service.run_job(job.id)

    assert isos.requested_keys == ["ubuntu"]
    assert worker.calls == [(job.id, Path("/dev/sdb"), [Path("/isos/ubuntu.iso")])]
    assert job.status == JobStatus.COMPLETED
    assert job.drives[0].status == JobStatus.COMPLETED
    assert job.drives[0].stage == JobStage.COMPLETE


def test_run_job_keeps_unrelated_drive_running_when_one_drive_fails():
    worker = FakeWorker(failures={Path("/dev/sdb")})
    job_service = service([device("/dev/sdb"), device("/dev/sdc")], worker=worker)
    job = job_service.create_job(
        [Path("/dev/sdb"), Path("/dev/sdc")],
        ["ubuntu"],
        {"/dev/sdb": "CONFIRMED", "/dev/sdc": "CONFIRMED"},
    )

    job_service.run_job(job.id)

    drives = {drive.device.path: drive for drive in job.drives}
    assert drives[Path("/dev/sdb")].status == JobStatus.FAILED
    assert drives[Path("/dev/sdb")].stage == JobStage.FAILED
    assert drives[Path("/dev/sdc")].status == JobStatus.COMPLETED
    assert drives[Path("/dev/sdc")].stage == JobStage.COMPLETE
    assert job.status == JobStatus.FAILED
    assert {call[1] for call in worker.calls} == {Path("/dev/sdb"), Path("/dev/sdc")}
    assert any(
        event.device_path == "/dev/sdb" and event.stage == JobStage.FAILED for event in job.events
    )


def test_run_job_handles_non_runtime_worker_failure_without_stopping_other_drives():
    worker = FakeWorker(value_failures={Path("/dev/sdb")})
    job_service = service([device("/dev/sdb"), device("/dev/sdc")], worker=worker)
    job = job_service.create_job(
        [Path("/dev/sdb"), Path("/dev/sdc")],
        ["ubuntu"],
        {"/dev/sdb": "CONFIRMED", "/dev/sdc": "CONFIRMED"},
    )

    job_service.run_job(job.id)

    drives = {drive.device.path: drive for drive in job.drives}
    assert drives[Path("/dev/sdb")].status == JobStatus.FAILED
    assert drives[Path("/dev/sdb")].stage == JobStage.FAILED
    assert drives[Path("/dev/sdb")].error == "invalid /dev/sdb"
    assert drives[Path("/dev/sdc")].status == JobStatus.COMPLETED
    assert drives[Path("/dev/sdc")].stage == JobStage.COMPLETE
    assert job.status == JobStatus.FAILED
    assert any(
        event.device_path == "/dev/sdb"
        and event.stage == JobStage.FAILED
        and event.message == "invalid /dev/sdb"
        for event in job.events
    )


def test_run_job_refuses_when_no_ready_iso_paths():
    worker = FakeWorker()
    job_service = service([device("/dev/sdb"), device("/dev/sdc")], worker=worker, isos=FakeIsoService([]))
    job = job_service.create_job(
        [Path("/dev/sdb"), Path("/dev/sdc")],
        ["ubuntu"],
        {"/dev/sdb": "CONFIRMED", "/dev/sdc": "CONFIRMED"},
    )

    job_service.run_job(job.id)

    assert worker.calls == []
    assert job.status == JobStatus.FAILED
    assert all(drive.status == JobStatus.FAILED for drive in job.drives)
    assert all(drive.stage == JobStage.FAILED for drive in job.drives)
    assert {drive.error for drive in job.drives} == {"No ready ISO files selected"}
    assert [event.stage for event in job.events] == [JobStage.FAILED, JobStage.FAILED]
    assert all(event.message == "No ready ISO files selected" for event in job.events)
