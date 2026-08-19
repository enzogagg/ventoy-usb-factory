from pathlib import Path

from conftest import FakeCommandRunner

from ventoy_usb_factory.devices import LinuxDeviceService
from ventoy_usb_factory.models import SafetyStatus

LSBLK_ARGS = [
    "lsblk",
    "--json",
    "--bytes",
    "--output",
    "NAME,PATH,TYPE,RM,TRAN,SIZE,MODEL,VENDOR,SERIAL,MOUNTPOINTS,FSTYPE,LABEL",
]


def test_list_devices_marks_usb_without_system_mountpoints_eligible(command_result):
    stdout = """
    {
      "blockdevices": [
        {"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"tran":"usb","size":16000000000,"model":"Flash","vendor":"USB","serial":"ABC","children":[
          {"name":"sdb1","path":"/dev/sdb1","type":"part","mountpoints":["/media/user/OLD"],"fstype":"vfat","label":"OLD"}
        ]}
      ]
    }
    """
    runner = FakeCommandRunner([command_result(LSBLK_ARGS, stdout=stdout)])
    service = LinuxDeviceService(runner)

    devices = service.list_devices()

    assert runner.calls == [LSBLK_ARGS]
    assert len(devices) == 1
    assert devices[0].path == Path("/dev/sdb")
    assert devices[0].safety == SafetyStatus.ELIGIBLE
    assert devices[0].partitions[0].mountpoints == [Path("/media/user/OLD")]


def test_list_devices_rejects_system_disk(command_result):
    stdout = """
    {"blockdevices":[{"name":"sda","path":"/dev/sda","type":"disk","rm":false,"tran":"sata","size":512000000000,"model":"SSD","vendor":"ATA","serial":"SYS","children":[
      {"name":"sda2","path":"/dev/sda2","type":"part","mountpoints":["/"],"fstype":"ext4","label":"root"}
    ]}]}
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(LSBLK_ARGS, stdout=stdout)]))

    devices = service.list_devices()

    assert devices[0].safety == SafetyStatus.UNSAFE_SYSTEM_DISK


def test_list_devices_rejects_non_removable_disk(command_result):
    stdout = """
    {"blockdevices":[{"name":"sdc","path":"/dev/sdc","type":"disk","rm":false,"tran":"sata","size":1000000000,"model":"Disk","vendor":"ATA","serial":"D1","children":[]}]}
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(LSBLK_ARGS, stdout=stdout)]))

    devices = service.list_devices()

    assert devices[0].safety == SafetyStatus.NOT_REMOVABLE


def test_list_devices_rejects_non_removable_usb_disk(command_result):
    stdout = """
    {"blockdevices":[{"name":"sdd","path":"/dev/sdd","type":"disk","rm":false,"tran":"usb","size":1000000000,"model":"External","vendor":"USB","serial":"D2","children":[]}]}
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(LSBLK_ARGS, stdout=stdout)]))

    devices = service.list_devices()

    assert devices[0].safety == SafetyStatus.NOT_REMOVABLE


def test_list_devices_rejects_nested_system_mountpoint(command_result):
    stdout = """
    {"blockdevices":[{"name":"sde","path":"/dev/sde","type":"disk","rm":true,"tran":"usb","size":1000000000,"model":"Disk","vendor":"USB","serial":"D3","children":[
      {"name":"sde1","path":"/dev/sde1","type":"part","mountpoints":[],"children":[
        {"name":"cryptroot","path":"/dev/mapper/cryptroot","type":"crypt","mountpoints":["/"],"fstype":"ext4","label":"root"}
      ]}
    ]}]}
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(LSBLK_ARGS, stdout=stdout)]))

    devices = service.list_devices()

    assert devices[0].safety == SafetyStatus.UNSAFE_SYSTEM_DISK


def test_list_devices_rejects_boot_efi_mountpoint(command_result):
    stdout = """
    {"blockdevices":[{"name":"sdf","path":"/dev/sdf","type":"disk","rm":true,"tran":"usb","size":1000000000,"model":"Disk","vendor":"USB","serial":"D4","children":[
      {"name":"sdf1","path":"/dev/sdf1","type":"part","mountpoints":["/boot/efi"],"fstype":"vfat","label":"EFI"}
    ]}]}
    """
    service = LinuxDeviceService(FakeCommandRunner([command_result(LSBLK_ARGS, stdout=stdout)]))

    devices = service.list_devices()

    assert devices[0].safety == SafetyStatus.UNSAFE_SYSTEM_DISK
