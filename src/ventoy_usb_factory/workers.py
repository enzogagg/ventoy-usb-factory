from collections.abc import Callable
from pathlib import Path

from ventoy_usb_factory.commands import CommandRunner
from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.models import JobEvent, JobStage, UsbDevice


class DriveWorker:
    def __init__(self, config: AppConfig, runner: CommandRunner, devices: LinuxDeviceService):
        self.config = config
        self.runner = runner
        self.devices = devices

    def prepare_drive(
        self,
        job_id: str,
        device: UsbDevice,
        iso_paths: list[Path],
        emit: Callable[[JobEvent], None],
    ) -> None:
        self._emit(emit, job_id, device, JobStage.REVALIDATING, "Revalidating selected device")
        current = self.devices.find_eligible_by_path(device.path)
        if current is None:
            raise RuntimeError(f"Device {device.path} is no longer eligible or changed identity")
        if not self._is_same_device(current, device):
            raise RuntimeError(f"Device {device.path} is no longer eligible or changed identity")

        mount_dir = self._safe_mount_dir(device)

        self._emit(emit, job_id, device, JobStage.UNMOUNTING, "Unmounting existing partitions")
        for partition in device.partitions:
            if partition.mountpoints:
                self._run(["umount", str(partition.path)])

        self._emit(emit, job_id, device, JobStage.INSTALLING_VENTOY, "Installing Ventoy")
        self._run(["sudo", str(self.config.ventoy_installer), "-I", str(device.path)])

        self._emit(emit, job_id, device, JobStage.WAITING_FOR_PARTITIONS, "Refreshing partition table")
        self._run(["partprobe", str(device.path)])
        refreshed = self.devices.find_eligible_by_path(device.path)
        if refreshed is None or not self._is_same_device(refreshed, device):
            raise RuntimeError(f"Device {device.path} is no longer eligible or changed identity")
        data_partition = self._data_partition(refreshed)

        self._emit(emit, job_id, device, JobStage.MOUNTING, "Mounting Ventoy data partition")
        self._run(["mount", str(data_partition), str(mount_dir)])

        self._emit(emit, job_id, device, JobStage.COPYING_ISOS, "Copying ISO files")
        for iso_path in iso_paths:
            self._run(["rsync", "-ah", "--progress", str(iso_path), str(mount_dir / iso_path.name)])

        self._emit(emit, job_id, device, JobStage.SYNCING, "Syncing filesystem buffers")
        self._run(["sync"])

        self._emit(emit, job_id, device, JobStage.UNMOUNTING_FINAL, "Unmounting Ventoy data partition")
        self._run(["umount", str(mount_dir)])
        self._emit(emit, job_id, device, JobStage.COMPLETE, "Drive complete")

    def _run(self, args: list[str]) -> None:
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.config.log_dir / "commands.log"
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"START {args!r}\n")
        result = self.runner.run(args)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"END returncode={result.returncode} {args!r}\n")
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"Command failed: {args}")

    def _is_same_device(self, current: UsbDevice, confirmed: UsbDevice) -> bool:
        return (
            current.path,
            current.name,
            current.model,
            current.vendor,
            current.serial,
            current.size_bytes,
            current.removable,
            current.transport,
        ) == (
            confirmed.path,
            confirmed.name,
            confirmed.model,
            confirmed.vendor,
            confirmed.serial,
            confirmed.size_bytes,
            confirmed.removable,
            confirmed.transport,
        )

    def _data_partition(self, device: UsbDevice) -> Path:
        partition_ones = [partition for partition in device.partitions if partition.name.endswith("1")]
        if partition_ones:
            return partition_ones[0].path
        if len(device.partitions) == 1:
            return device.partitions[0].path
        raise RuntimeError(f"No usable data partition found for {device.path}")

    def _safe_mount_dir(self, device: UsbDevice) -> Path:
        if self.config.log_dir.is_symlink():
            raise RuntimeError(f"Unsafe mount directory: {self.config.log_dir}")
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        resolved_log_dir = self.config.log_dir.resolve()

        mount_root = resolved_log_dir / "mnt"
        if mount_root.is_symlink():
            raise RuntimeError(f"Unsafe mount directory: {mount_root}")
        mount_root.mkdir(parents=True, exist_ok=True)
        resolved_root = mount_root.resolve()
        mount_dir = mount_root / device.name
        if mount_dir.is_symlink():
            raise RuntimeError(f"Unsafe mount directory: {mount_dir}")
        mount_dir.mkdir(parents=True, exist_ok=True)
        resolved_mount_dir = mount_dir.resolve()
        if not resolved_mount_dir.is_relative_to(resolved_root):
            raise RuntimeError(f"Unsafe mount directory: {mount_dir}")
        return mount_dir

    def _emit(
        self,
        emit: Callable[[JobEvent], None],
        job_id: str,
        device: UsbDevice,
        stage: JobStage,
        message: str,
    ) -> None:
        emit(JobEvent(job_id=job_id, device_path=str(device.path), stage=stage, message=message))
