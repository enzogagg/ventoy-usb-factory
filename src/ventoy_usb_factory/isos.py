from pathlib import Path

from ventoy_usb_factory.config import AppConfig
from ventoy_usb_factory.models import IsoEntry, IsoStatus

REQUIRED_ISOS = {
    "windows10": ("Windows 10", ("win10", "windows10")),
    "windows11": ("Windows 11", ("win11", "windows11")),
    "ubuntu": ("Ubuntu", ("ubuntu", "desktop", "amd64")),
}


class IsoService:
    def __init__(self, config: AppConfig):
        self.config = config

    def list_isos(self) -> list[IsoEntry]:
        self.config.iso_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self.config.iso_dir.glob("*.iso"))
        return [
            self._entry_for(key, name, tokens, files)
            for key, (name, tokens) in REQUIRED_ISOS.items()
        ]

    def ready_iso_paths(self, keys: list[str]) -> list[Path]:
        requested = set(keys)
        return [
            entry.path
            for entry in self.list_isos()
            if entry.key in requested and entry.path is not None and entry.status == IsoStatus.READY
        ]

    def _entry_for(
        self,
        key: str,
        name: str,
        tokens: tuple[str, ...],
        files: list[Path],
    ) -> IsoEntry:
        match = self._find_local(key, tokens, files)
        if match is not None:
            return IsoEntry(
                key=key,
                name=name,
                status=IsoStatus.READY,
                path=match,
                size_bytes=match.stat().st_size,
                version=match.stem,
                message="Local ISO ready",
            )

        if key == "ubuntu":
            return IsoEntry(
                key=key,
                name=name,
                status=IsoStatus.DOWNLOAD_AVAILABLE,
                path=None,
                size_bytes=None,
                version="latest-lts",
                message="Official Ubuntu LTS desktop ISO download is available.",
            )

        return IsoEntry(
            key=key,
            name=name,
            status=IsoStatus.MANUAL_REQUIRED,
            path=None,
            size_bytes=None,
            version=None,
            message="Download this ISO from Microsoft and place it in the ISO folder.",
        )

    def _find_local(self, key: str, tokens: tuple[str, ...], files: list[Path]) -> Path | None:
        for file in files:
            filename = file.name.lower()
            if key == "ubuntu":
                if all(token in filename for token in tokens):
                    return file
            elif any(token in filename for token in tokens):
                return file
        return None
