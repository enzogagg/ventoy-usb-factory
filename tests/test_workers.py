from pathlib import Path

import pytest
from conftest import FakeCommandRunner

from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.models import BlockPartition, JobEvent, JobStage, SafetyStatus, UsbDevice
from ventoy_usb_factory.workers import DriveWorker


def config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        "127.0.0.1",
        8080,
        tmp_path / "isos",
        tmp_path / "logs",
        tmp_path / "ventoy" / "Ventoy2Disk.sh",
        2,
    )


def eligible_device() -> UsbDevice:
    return UsbDevice(
        Path("/dev/sdb"),
        "sdb",
        "Flash",
        "USB",
        "ABC",
        16000000000,
        True,
        "usb",
        [BlockPartition("sdb1", Path("/dev/sdb1"), [Path("/media/old")])],
        SafetyStatus.ELIGIBLE,
        "eligible removable USB storage",
    )


def test_prepare_drive_uses_argument_arrays_calls_installer_and_completes(
    tmp_path: Path, command_result
):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    runner = FakeCommandRunner(
        [
            command_result(["lsblk"], stdout=lsblk_stdout),
            command_result(["umount"]),
            command_result(["ventoy"]),
            command_result(["partprobe"]),
            command_result(["mount"]),
            command_result(["rsync"]),
            command_result(["sync"]),
            command_result(["umount"]),
        ]
    )
    events: list[JobEvent] = []
    app_config = config(tmp_path)

    worker = DriveWorker(app_config, runner, LinuxDeviceService(runner))
    worker.prepare_drive("job-1", eligible_device(), [tmp_path / "ubuntu.iso"], events.append)

    assert events[0].stage == JobStage.REVALIDATING
    assert events[-1].stage == JobStage.COMPLETE
    assert all(isinstance(call, list) for call in runner.calls)
    assert ["sudo", str(app_config.ventoy_installer), "-I", "/dev/sdb"] in runner.calls
    assert ["umount", "/dev/sdb1"] in runner.calls
    assert ["partprobe", "/dev/sdb"] in runner.calls
    assert ["sync"] in runner.calls


@pytest.mark.parametrize(
    ("lsblk_stdout", "message"),
    [
        ('{"blockdevices":[]}', "no longer eligible"),
        (
            '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":32000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}',
            "no longer eligible",
        ),
        (
            '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":false,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}',
            "no longer eligible",
        ),
    ],
)
def test_prepare_drive_refuses_missing_changed_or_non_eligible_device(
    tmp_path: Path, command_result, lsblk_stdout: str, message: str
):
    runner = FakeCommandRunner([command_result(["lsblk"], stdout=lsblk_stdout)])
    events: list[JobEvent] = []
    worker = DriveWorker(config(tmp_path), runner, LinuxDeviceService(runner))

    with pytest.raises(RuntimeError, match=message):
        worker.prepare_drive("job-1", eligible_device(), [], events.append)

    assert events[0].stage == JobStage.REVALIDATING
