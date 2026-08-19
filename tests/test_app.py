from pathlib import Path

from conftest import FakeCommandRunner
from fastapi.testclient import TestClient

from ventoy_usb_factory.app import create_app
from ventoy_usb_factory.config import AppConfig


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
