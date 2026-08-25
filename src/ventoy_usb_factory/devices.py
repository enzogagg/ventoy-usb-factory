import json
from pathlib import Path

from ventoy_usb_factory.commands import CommandRunner
from ventoy_usb_factory.models import BlockPartition, SafetyStatus, UsbDevice

LSBLK_ARGS = [
    "lsblk",
    "--json",
    "--bytes",
    "--output",
    "NAME,PATH,TYPE,RM,TRAN,SIZE,MODEL,VENDOR,SERIAL,MOUNTPOINTS,FSTYPE,LABEL",
]
SYSTEM_MOUNTPOINTS = {
    Path("/"),
    Path("/boot"),
    Path("/boot/efi"),
    Path("/home"),
    Path("/var"),
    Path("/usr"),
}


class LinuxDeviceService:
    def __init__(self, runner: CommandRunner):
        self.runner = runner

    def list_devices(self) -> list[UsbDevice]:
        result = self.runner.run(LSBLK_ARGS)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "lsblk failed")

        payload = json.loads(result.stdout)
        return [
            self._device_from_raw(raw)
            for raw in payload.get("blockdevices", [])
            if raw.get("type") == "disk"
        ]

    def find_eligible_by_path(self, path: Path) -> UsbDevice | None:
        for device in self.list_devices():
            if device.path == path and device.safety == SafetyStatus.ELIGIBLE:
                return device
        return None

    def _device_from_raw(self, raw: dict) -> UsbDevice:
        partitions = [self._partition_from_raw(child) for child in self._iter_children(raw)]
        safety, reason = self._classify(raw, partitions)
        return UsbDevice(
            path=Path(raw["path"]),
            name=str(raw["name"]),
            model=raw.get("model"),
            vendor=raw.get("vendor"),
            serial=raw.get("serial"),
            size_bytes=int(raw.get("size") or 0),
            removable=bool(raw.get("rm")),
            transport=raw.get("tran"),
            partitions=partitions,
            safety=safety,
            safety_reason=reason,
        )

    def _partition_from_raw(self, raw: dict) -> BlockPartition:
        mountpoints = [Path(mount) for mount in raw.get("mountpoints") or [] if mount]
        return BlockPartition(
            name=str(raw["name"]),
            path=Path(raw["path"]),
            mountpoints=mountpoints,
            fstype=raw.get("fstype"),
            label=raw.get("label"),
        )

    def _iter_children(self, raw: dict) -> list[dict]:
        children = []
        for child in raw.get("children") or []:
            children.append(child)
            children.extend(self._iter_children(child))
        return children

    def _classify(
        self, raw: dict, partitions: list[BlockPartition]
    ) -> tuple[SafetyStatus, str]:
        mountpoints = {mount for partition in partitions for mount in partition.mountpoints}
        if any(self._is_system_mountpoint(mount) for mount in mountpoints):
            return SafetyStatus.UNSAFE_SYSTEM_DISK, "contains a system mountpoint"
        if not bool(raw.get("rm")) or raw.get("tran") != "usb":
            return SafetyStatus.NOT_REMOVABLE, "device is not removable USB storage"
        return SafetyStatus.ELIGIBLE, "eligible removable USB storage"

    def _is_system_mountpoint(self, mountpoint: Path) -> bool:
        return mountpoint in SYSTEM_MOUNTPOINTS or any(
            system_mount in mountpoint.parents for system_mount in SYSTEM_MOUNTPOINTS - {Path("/")}
        )


class UnsupportedDeviceService:
    def list_devices(self) -> list[UsbDevice]:
        return []

    def find_eligible_by_path(self, path: Path) -> UsbDevice | None:
        return None
