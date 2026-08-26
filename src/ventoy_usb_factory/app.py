import json
import os
import platform
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from threading import Thread
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ventoy_usb_factory.commands import CommandRunner, SubprocessCommandRunner
from ventoy_usb_factory.config import AppConfig, ensure_runtime_dirs, load_config
from ventoy_usb_factory.devices import LinuxDeviceService, UnsupportedDeviceService
from ventoy_usb_factory.isos import IsoService
from ventoy_usb_factory.jobs import JobService
from ventoy_usb_factory.models import JobStatus
from ventoy_usb_factory.workers import DriveWorker

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


class CreateJobRequest(BaseModel):
    device_paths: list[str]
    iso_keys: list[str]
    confirmations: dict[str, str]


def runtime_status() -> dict[str, Any]:
    platform_name = platform.system()
    root_required = platform_name == "Linux"
    running_as_root = bool(getattr(os, "geteuid", lambda: 1)() == 0)
    can_prepare = not root_required or running_as_root
    message = (
        "Start with sudo to install Ventoy on USB drives."
        if root_required and not running_as_root
        else "Ready to prepare eligible USB drives."
    )
    return {
        "platform": platform_name,
        "root_required": root_required,
        "running_as_root": running_as_root,
        "can_prepare": can_prepare,
        "message": message,
    }


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
    uses_default_runner = runner is None
    runner = runner or SubprocessCommandRunner()
    device_service = (
        UnsupportedDeviceService()
        if uses_default_runner and platform.system() != "Linux"
        else LinuxDeviceService(runner)
    )
    iso_service = IsoService(config)
    worker = DriveWorker(config, runner, device_service)
    job_service = JobService(device_service, iso_service, worker, config.max_concurrent_jobs)
    app = FastAPI(title="Ventoy USB Factory")
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.get("/")
    def dashboard(request: Request):
        return templates.TemplateResponse(request, "dashboard.html")

    @app.get("/api/devices")
    def api_devices():
        return encode([device for device in device_service.list_devices() if device.safety.value == "eligible"])

    @app.get("/api/status")
    def api_status():
        return runtime_status()

    @app.get("/api/isos")
    def api_isos():
        return encode(iso_service.list_isos())

    @app.post("/api/isos/refresh")
    def api_isos_refresh():
        return encode(iso_service.list_isos())

    @app.post("/api/jobs")
    def api_create_job(request: CreateJobRequest):
        status = runtime_status()
        if not status["can_prepare"]:
            raise HTTPException(status_code=403, detail=status["message"])
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
    uvicorn.run(
        "ventoy_usb_factory.app:create_app",
        factory=True,
        host=config.host,
        port=config.port,
    )
