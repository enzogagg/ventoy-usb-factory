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


def nvme_device() -> UsbDevice:
    return UsbDevice(
        Path("/dev/nvme0n1"),
        "nvme0n1",
        "FastFlash",
        "USB",
        "NVME-ABC",
        64000000000,
        True,
        "usb",
        [],
        SafetyStatus.ELIGIBLE,
        "eligible removable USB storage",
    )


def successful_results(
    command_result,
    initial_lsblk_stdout: str,
    refreshed_lsblk_stdout: str,
    iso_count: int = 1,
    unmount_count: int = 1,
):
    return [
        command_result(["lsblk"], stdout=initial_lsblk_stdout),
        *[command_result(["umount"]) for _ in range(unmount_count)],
        command_result(["ventoy"]),
        command_result(["partprobe"]),
        command_result(["lsblk"], stdout=refreshed_lsblk_stdout),
        command_result(["mount"]),
        *[command_result(["rsync"]) for _ in range(iso_count)],
        command_result(["sync"]),
        command_result(["umount"]),
    ]


def test_prepare_drive_uses_argument_arrays_calls_installer_and_completes(
    tmp_path: Path, command_result
):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    refreshed_lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[
      {"name":"sdb1","path":"/dev/sdb1","type":"part","mountpoints":[],"fstype":"exfat","label":"Ventoy"}
    ]}]}
    """
    runner = FakeCommandRunner(successful_results(command_result, lsblk_stdout, refreshed_lsblk_stdout))
    events: list[JobEvent] = []
    app_config = config(tmp_path)

    worker = DriveWorker(app_config, runner, LinuxDeviceService(runner))
    worker.prepare_drive("job-1", eligible_device(), [tmp_path / "ubuntu.iso"], events.append)

    assert events[0].stage == JobStage.REVALIDATING
    assert events[-1].stage == JobStage.COMPLETE
    assert all(isinstance(call, list) for call in runner.calls)
    assert len([call for call in runner.calls if call and call[0] == "lsblk"]) == 2
    assert ["sudo", str(app_config.ventoy_installer), "-I", "/dev/sdb"] in runner.calls
    assert ["umount", "/dev/sdb1"] in runner.calls
    assert ["partprobe", "/dev/sdb"] in runner.calls
    assert ["mount", "/dev/sdb1", str(tmp_path / "logs" / "mnt" / "sdb")] in runner.calls
    assert ["sync"] in runner.calls


@pytest.mark.parametrize(
    "lsblk_stdout",
    [
        '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"OtherFlash","vendor":"USB","serial":"ABC","children":[]}]}',
        '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"OtherVendor","serial":"ABC","children":[]}]}',
        '{"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":null,"children":[]}]}',
    ],
)
def test_prepare_drive_refuses_identity_mismatch_before_destructive_commands(
    tmp_path: Path, command_result, lsblk_stdout: str
):
    runner = FakeCommandRunner([command_result(["lsblk"], stdout=lsblk_stdout)])
    events: list[JobEvent] = []
    worker = DriveWorker(config(tmp_path), runner, LinuxDeviceService(runner))

    with pytest.raises(RuntimeError, match="changed identity"):
        worker.prepare_drive("job-1", eligible_device(), [], events.append)

    assert len(runner.calls) == 1


def test_prepare_drive_logs_before_and_after_commands(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    refreshed_lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[
      {"name":"sdb1","path":"/dev/sdb1","type":"part","mountpoints":[],"fstype":"exfat","label":"Ventoy"}
    ]}]}
    """
    app_config = config(tmp_path)
    runner = FakeCommandRunner(successful_results(command_result, lsblk_stdout, refreshed_lsblk_stdout))
    worker = DriveWorker(app_config, runner, LinuxDeviceService(runner))

    worker.prepare_drive("job-1", eligible_device(), [tmp_path / "ubuntu.iso"], lambda event: None)

    log_text = (app_config.log_dir / "commands.log").read_text(encoding="utf-8")
    assert "START ['sudo'" in log_text
    assert "END returncode=0 ['sudo'" in log_text


def test_prepare_drive_emits_live_command_output(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    refreshed_lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[
      {"name":"sdb1","path":"/dev/sdb1","type":"part","mountpoints":[],"fstype":"exfat","label":"Ventoy"}
    ]}]}
    """
    runner = FakeCommandRunner(
        [
            command_result(["lsblk"], stdout=lsblk_stdout),
            command_result(["umount"]),
            command_result(["ventoy"], stdout="formatting disk\nwriting bootloader\n", stderr="warning line\n"),
            command_result(["partprobe"]),
            command_result(["lsblk"], stdout=refreshed_lsblk_stdout),
            command_result(["mount"]),
            command_result(["rsync"], stdout="ubuntu.iso 42%\n"),
            command_result(["sync"]),
            command_result(["umount"]),
        ]
    )
    events: list[JobEvent] = []
    worker = DriveWorker(config(tmp_path), runner, LinuxDeviceService(runner))

    worker.prepare_drive("job-1", eligible_device(), [tmp_path / "ubuntu.iso"], events.append)

    assert any(
        event.stage == JobStage.INSTALLING_VENTOY and event.message == "stdout: formatting disk"
        for event in events
    )
    assert any(
        event.stage == JobStage.INSTALLING_VENTOY and event.message == "stdout: writing bootloader"
        for event in events
    )
    assert any(
        event.stage == JobStage.INSTALLING_VENTOY and event.message == "stderr: warning line"
        for event in events
    )
    assert any(
        event.stage == JobStage.COPYING_ISOS and event.message == "stdout: ubuntu.iso 42%"
        for event in events
    )


def test_prepare_drive_emits_started_command_line(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    refreshed_lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[
      {"name":"sdb1","path":"/dev/sdb1","type":"part","mountpoints":[],"fstype":"exfat","label":"Ventoy"}
    ]}]}
    """
    runner = FakeCommandRunner(successful_results(command_result, lsblk_stdout, refreshed_lsblk_stdout))
    events: list[JobEvent] = []
    app_config = config(tmp_path)
    worker = DriveWorker(app_config, runner, LinuxDeviceService(runner))

    worker.prepare_drive("job-1", eligible_device(), [tmp_path / "ubuntu.iso"], events.append)

    assert any(
        event.stage == JobStage.INSTALLING_VENTOY
        and event.message == f"command: sudo {app_config.ventoy_installer} -I /dev/sdb"
        for event in events
    )


def test_prepare_drive_unmounts_mounted_partition_when_rsync_fails(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    refreshed_lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[
      {"name":"sdb1","path":"/dev/sdb1","type":"part","mountpoints":[],"fstype":"exfat","label":"Ventoy"}
    ]}]}
    """
    app_config = config(tmp_path)
    mount_dir = tmp_path / "logs" / "mnt" / "sdb"
    runner = FakeCommandRunner(
        [
            command_result(["lsblk"], stdout=lsblk_stdout),
            command_result(["umount"]),
            command_result(["ventoy"]),
            command_result(["partprobe"]),
            command_result(["lsblk"], stdout=refreshed_lsblk_stdout),
            command_result(["mount"]),
            command_result(["rsync"], stderr="copy failed", returncode=23),
            command_result(["umount"]),
        ]
    )
    worker = DriveWorker(app_config, runner, LinuxDeviceService(runner))

    with pytest.raises(RuntimeError, match="copy failed"):
        worker.prepare_drive("job-1", eligible_device(), [tmp_path / "ubuntu.iso"], lambda event: None)

    assert ["umount", str(mount_dir)] in runner.calls


@pytest.mark.parametrize("exception", [FileNotFoundError("missing binary"), ValueError("bad args")])
def test_run_logs_end_when_command_runner_raises(tmp_path: Path, exception):
    class RaisingRunner:
        def run(self, args: list[str], timeout: int | None = None, on_output=None):
            raise exception

    app_config = config(tmp_path)
    worker = DriveWorker(app_config, RaisingRunner(), LinuxDeviceService(RaisingRunner()))

    with pytest.raises(type(exception), match=str(exception)):
        worker._run(["missing-command"])

    log_text = (app_config.log_dir / "commands.log").read_text(encoding="utf-8")
    assert "START ['missing-command']" in log_text
    assert f"END exception={type(exception).__name__}: {exception} ['missing-command']" in log_text


def test_prepare_drive_uses_p1_suffix_for_numeric_device_names(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","rm":true,"tran":"usb","size":64000000000,"model":"FastFlash","vendor":"USB","serial":"NVME-ABC","children":[]}]}
    """
    refreshed_lsblk_stdout = """
    {"blockdevices":[{"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","rm":true,"tran":"usb","size":64000000000,"model":"FastFlash","vendor":"USB","serial":"NVME-ABC","children":[
      {"name":"nvme0n1p1","path":"/dev/nvme0n1p1","type":"part","mountpoints":[],"fstype":"exfat","label":"Ventoy"}
    ]}]}
    """
    runner = FakeCommandRunner(
        successful_results(
            command_result, lsblk_stdout, refreshed_lsblk_stdout, iso_count=0, unmount_count=0
        )
    )
    worker = DriveWorker(config(tmp_path), runner, LinuxDeviceService(runner))

    worker.prepare_drive("job-1", nvme_device(), [], lambda event: None)

    mount_calls = [call for call in runner.calls if call and call[0] == "mount"]
    assert mount_calls == [["mount", "/dev/nvme0n1p1", str(tmp_path / "logs" / "mnt" / "nvme0n1")]]


def test_prepare_drive_refuses_to_mount_without_refreshed_partition(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    runner = FakeCommandRunner(
        [
            command_result(["lsblk"], stdout=lsblk_stdout),
            command_result(["umount"]),
            command_result(["ventoy"]),
            command_result(["partprobe"]),
            command_result(["lsblk"], stdout=lsblk_stdout),
        ]
    )
    worker = DriveWorker(config(tmp_path), runner, LinuxDeviceService(runner))

    with pytest.raises(RuntimeError, match="No usable data partition"):
        worker.prepare_drive("job-1", eligible_device(), [], lambda event: None)

    assert not any(call and call[0] == "mount" for call in runner.calls)


def test_prepare_drive_rejects_symlink_mount_dir(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    app_config = config(tmp_path)
    mount_root = app_config.log_dir / "mnt"
    mount_root.mkdir(parents=True)
    (mount_root / "sdb").symlink_to(tmp_path)
    runner = FakeCommandRunner(
        [
            command_result(["lsblk"], stdout=lsblk_stdout),
            command_result(["umount"]),
            command_result(["ventoy"]),
            command_result(["partprobe"]),
        ]
    )
    worker = DriveWorker(app_config, runner, LinuxDeviceService(runner))

    with pytest.raises(RuntimeError, match="Unsafe mount directory"):
        worker.prepare_drive("job-1", eligible_device(), [], lambda event: None)

    assert not any(call and call[0] == "mount" for call in runner.calls)


def test_prepare_drive_rejects_symlink_mount_root(tmp_path: Path, command_result):
    lsblk_stdout = """
    {"blockdevices":[{"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[]}]}
    """
    app_config = config(tmp_path)
    app_config.log_dir.mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    (app_config.log_dir / "mnt").symlink_to(tmp_path / "outside")
    runner = FakeCommandRunner([command_result(["lsblk"], stdout=lsblk_stdout)])
    worker = DriveWorker(app_config, runner, LinuxDeviceService(runner))

    with pytest.raises(RuntimeError, match="Unsafe mount directory"):
        worker.prepare_drive("job-1", eligible_device(), [], lambda event: None)

    assert not any(call and call[0] == "umount" for call in runner.calls)


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
