from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock, Semaphore
from uuid import uuid4

from ventoy_usb_factory.models import (
    DriveJob,
    JobEvent,
    JobStage,
    JobStatus,
    PreparationJob,
    SafetyStatus,
)


class JobService:
    def __init__(self, devices, isos, worker, max_concurrent_jobs: int):
        self.devices = devices
        self.isos = isos
        self.worker = worker
        self.max_concurrent_jobs = max(1, max_concurrent_jobs)
        self._jobs: dict[str, PreparationJob] = {}
        self._lock = Lock()

    def create_job(
        self,
        device_paths: list[Path],
        iso_keys: list[str],
        confirmations: dict[str, str],
        max_concurrent_drives: int | None = None,
    ) -> PreparationJob:
        if not device_paths:
            raise ValueError("At least one device is required")
        if len(set(device_paths)) != len(device_paths):
            raise ValueError("Duplicate device paths are not allowed")

        current_devices = {device.path: device for device in self.devices.list_devices()}
        drives: list[DriveJob] = []
        for path in device_paths:
            device = current_devices.get(path)
            if device is None or device.safety != SafetyStatus.ELIGIBLE:
                raise ValueError(f"Device {path} is not eligible")
            if confirmations.get(str(path)) != "CONFIRMED":
                raise ValueError(f"Exact confirmation required for {path}")
            drives.append(DriveJob(device=device))

        concurrency = max(1, int(max_concurrent_drives or self.max_concurrent_jobs))
        concurrency = min(concurrency, len(drives))
        job = PreparationJob(
            id=str(uuid4()),
            drives=drives,
            iso_keys=list(iso_keys),
            max_concurrent_drives=concurrency,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> PreparationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[PreparationJob]:
        with self._lock:
            return list(self._jobs.values())

    def run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            raise ValueError(f"Unknown job: {job_id}")

        iso_paths = self.isos.ready_iso_paths(job.iso_keys)
        if not iso_paths:
            message = "No ready ISO files selected"
            with self._lock:
                job.status = JobStatus.FAILED
                for drive in job.drives:
                    drive.status = JobStatus.FAILED
                    drive.stage = JobStage.FAILED
                    drive.error = message
                    job.events.append(
                        JobEvent(
                            job_id=job.id,
                            device_path=str(drive.device.path),
                            stage=JobStage.FAILED,
                            message=message,
                        )
                    )
            return

        job.status = JobStatus.RUNNING
        semaphore = Semaphore(job.max_concurrent_drives)

        def run_drive(drive: DriveJob) -> None:
            with semaphore:
                drive.status = JobStatus.RUNNING

                def emit(event: JobEvent) -> None:
                    with self._lock:
                        job.events.append(event)
                        drive.stage = event.stage

                try:
                    self.worker.prepare_drive(job.id, drive.device, iso_paths, emit)
                except Exception as exc:  # noqa: BLE001 - isolate each drive worker failure.
                    drive.status = JobStatus.FAILED
                    drive.stage = JobStage.FAILED
                    drive.error = str(exc)
                    emit(
                        JobEvent(
                            job_id=job.id,
                            device_path=str(drive.device.path),
                            stage=JobStage.FAILED,
                            message=str(exc),
                        )
                    )
                    return

                drive.status = JobStatus.COMPLETED
                drive.stage = JobStage.COMPLETE

        with ThreadPoolExecutor(max_workers=len(job.drives)) as executor:
            futures = [executor.submit(run_drive, drive) for drive in job.drives]
            for future in futures:
                future.result()

        if all(drive.status == JobStatus.COMPLETED for drive in job.drives):
            job.status = JobStatus.COMPLETED
        else:
            job.status = JobStatus.FAILED
