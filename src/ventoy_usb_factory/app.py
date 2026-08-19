import json
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from threading import Thread
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ventoy_usb_factory.commands import CommandRunner, SubprocessCommandRunner
from ventoy_usb_factory.config import AppConfig, ensure_runtime_dirs, load_config
from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.isos import IsoService
from ventoy_usb_factory.jobs import JobService
from ventoy_usb_factory.models import JobStatus
from ventoy_usb_factory.workers import DriveWorker


class CreateJobRequest(BaseModel):
    device_paths: list[str]
    iso_keys: list[str]
    confirmations: dict[str, str]


def encode(value: Any) -> Any:
    if is_dataclass(value):
        return encode(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
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
            job = job_service.create_job(
                [Path(path) for path in request.device_paths],
                request.iso_keys,
                request.confirmations,
            )
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
            last_event_index = 0
            while True:
                job = job_service.get_job(job_id)
                if job is None:
                    yield f"event: error\ndata: {json.dumps({'detail': 'Job not found'})}\n\n"
                    return

                while last_event_index < len(job.events):
                    event = job.events[last_event_index]
                    last_event_index += 1
                    yield f"data: {json.dumps(encode(event))}\n\n"

                if job.status not in {JobStatus.PENDING, JobStatus.RUNNING}:
                    return
                time.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def main() -> None:
    config_path = Path("config.yaml")
    config = load_config(config_path if config_path.exists() else None)
    uvicorn.run(create_app(config), host=config.host, port=config.port)
