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
    by_key = {entry.key: entry for entry in entries}
    assert by_key["windows10"].path == tmp_path / "Win10_22H2.iso"
    assert by_key["windows10"].size_bytes == 5
    assert by_key["windows10"].version == "Win10_22H2"
    assert by_key["windows10"].message == "Local ISO ready"


def test_list_isos_marks_windows_manual_when_missing(tmp_path):
    entries = IsoService(make_config(tmp_path)).list_isos()
    by_key = {entry.key: entry for entry in entries}

    assert by_key["windows10"].status == IsoStatus.MANUAL_REQUIRED
    assert "Microsoft" in by_key["windows10"].message
    assert by_key["windows11"].status == IsoStatus.MANUAL_REQUIRED
    assert "Microsoft" in by_key["windows11"].message


def test_ready_iso_paths_only_returns_ready_requested_files(tmp_path):
    (tmp_path / "ubuntu-24.04.3-desktop-amd64.iso").write_bytes(b"ubuntu")

    paths = IsoService(make_config(tmp_path)).ready_iso_paths(["ubuntu", "windows11"])

    assert paths == [tmp_path / "ubuntu-24.04.3-desktop-amd64.iso"]
