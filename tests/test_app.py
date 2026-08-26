import json
from pathlib import Path
from threading import Event, Thread

from conftest import FakeCommandRunner
from fastapi.testclient import TestClient

from ventoy_usb_factory.app import create_app
from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.models import DriveJob, JobEvent, JobStage, JobStatus, PreparationJob


def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        host="127.0.0.1",
        port=8080,
        iso_dir=tmp_path / "isos",
        log_dir=tmp_path / "logs",
        ventoy_installer=tmp_path / "ventoy" / "Ventoy2Disk.sh",
        max_concurrent_jobs=2,
    )


def test_api_lists_devices(tmp_path, command_result):
    stdout = '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}'
    app = create_app(app_config(tmp_path), FakeCommandRunner([command_result(["lsblk"], stdout=stdout)]))

    response = TestClient(app).get("/api/devices")

    assert response.status_code == 200
    assert response.json()[0]["path"] == "/dev/sdb"
    assert response.json()[0]["safety"] == "eligible"


def test_api_lists_isos(tmp_path):
    app = create_app(app_config(tmp_path))

    response = TestClient(app).get("/api/isos")

    assert response.status_code == 200
    assert {entry["key"] for entry in response.json()} == {"windows10", "windows11", "ubuntu"}


def test_api_devices_returns_empty_list_on_non_linux_without_lsblk(tmp_path, monkeypatch):
    monkeypatch.setattr("ventoy_usb_factory.app.platform.system", lambda: "Darwin")
    app = create_app(app_config(tmp_path))

    response = TestClient(app).get("/api/devices")

    assert response.status_code == 200
    assert response.json() == []


def test_main_runs_uvicorn_with_factory_string(tmp_path, monkeypatch):
    calls = []
    config = app_config(tmp_path)

    monkeypatch.setattr("ventoy_usb_factory.app.load_config", lambda path: config)
    monkeypatch.setattr("ventoy_usb_factory.app.uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs)))

    from ventoy_usb_factory.app import main

    main()

    assert calls == [
        (
            ("ventoy_usb_factory.app:create_app",),
            {"factory": True, "host": "127.0.0.1", "port": 8080},
        )
    ]


def test_dashboard_renders_safety_warning(tmp_path):
    response = TestClient(create_app(app_config(tmp_path))).get("/")

    assert response.status_code == 200
    assert "Ventoy USB Factory" in response.text
    assert "erases the selected USB drive" in response.text


def test_dashboard_script_avoids_dynamic_inner_html(tmp_path):
    response = TestClient(create_app(app_config(tmp_path))).get("/static/app.js")

    assert response.status_code == 200
    assert "innerHTML" not in response.text


def test_dashboard_script_preserves_iso_selection_after_first_load(tmp_path):
    response = TestClient(create_app(app_config(tmp_path))).get("/static/app.js")

    assert response.status_code == 200
    assert "initialIsoSelectionApplied" in response.text


def test_dashboard_script_uses_job_event_stream(tmp_path):
    response = TestClient(create_app(app_config(tmp_path))).get("/static/app.js")

    assert response.status_code == 200
    assert "new EventSource(`/api/jobs/${job.id}/events`)" in response.text
    assert "addEventListener(\"message\"" in response.text


def test_dashboard_script_uses_popup_confirmation_instead_of_text_fields(tmp_path):
    response = TestClient(create_app(app_config(tmp_path))).get("/static/app.js")

    assert response.status_code == 200
    assert "window.confirm" in response.text
    assert "CONFIRMED" in response.text
    assert "ERASE ${path}" not in response.text


def test_create_job_validation_returns_400_on_missing_confirmation(tmp_path, command_result):
    stdout = '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}'
    app = create_app(app_config(tmp_path), FakeCommandRunner([command_result(["lsblk"], stdout=stdout)]))

    response = TestClient(app).post(
        "/api/jobs",
        json={"device_paths": ["/dev/sdb"], "iso_keys": ["ubuntu"], "confirmations": {}},
    )

    assert response.status_code == 400
    assert "Exact confirmation required" in response.json()["detail"]


def test_missing_job_returns_404(tmp_path):
    app = create_app(app_config(tmp_path))

    response = TestClient(app).get("/api/jobs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_job_events_streams_events_appended_after_connection(
    tmp_path, command_result, monkeypatch
):
    worker_waiting = Event()
    worker_can_finish = Event()
    sse_polled_job = Event()
    stdout = '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}'

    class ControlledJobService:
        def __init__(self, devices, isos, worker, max_concurrent_jobs):
            self.devices = devices
            self.job = None

        def create_job(self, device_paths, iso_keys, confirmations):
            device = self.devices.list_devices()[0]
            self.job = PreparationJob(
                id="job-1",
                drives=[DriveJob(device=device)],
                iso_keys=list(iso_keys),
            )
            return self.job

        def run_job(self, job_id):
            assert self.job is not None
            self.job.status = JobStatus.RUNNING
            worker_waiting.set()
            assert worker_can_finish.wait(timeout=1)
            self.job.events.append(
                JobEvent(
                    job_id=job_id,
                    device_path=str(self.job.drives[0].device.path),
                    stage=JobStage.REVALIDATING,
                    message="streamed after connect",
                )
            )
            self.job.status = JobStatus.COMPLETED

        def get_job(self, job_id):
            if self.job is not None and self.job.status == JobStatus.RUNNING:
                sse_polled_job.set()
            return self.job if self.job is not None and self.job.id == job_id else None

        def list_jobs(self):
            return [self.job] if self.job is not None else []

    monkeypatch.setattr("ventoy_usb_factory.app.JobService", ControlledJobService)
    app = create_app(app_config(tmp_path), FakeCommandRunner([command_result(["lsblk"], stdout=stdout)]))
    client = TestClient(app)
    job_response = client.post(
        "/api/jobs",
        json={
            "device_paths": ["/dev/sdb"],
            "iso_keys": ["ubuntu"],
            "confirmations": {"/dev/sdb": "CONFIRMED"},
        },
    )
    job_id = job_response.json()["id"]
    assert worker_waiting.wait(timeout=1)

    body: list[str] = []

    def read_stream():
        response = client.get(f"/api/jobs/{job_id}/events")
        body.append(response.text)

    stream_thread = Thread(target=read_stream)
    stream_thread.start()
    assert sse_polled_job.wait(timeout=1)
    worker_can_finish.set()
    stream_thread.join(timeout=1)

    assert not stream_thread.is_alive()
    data_lines = [line for line in body[0].splitlines() if line.startswith("data: ")]
    assert json.loads(data_lines[0].removeprefix("data: "))["message"] == "streamed after connect"
