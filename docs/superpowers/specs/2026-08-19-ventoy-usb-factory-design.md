# Ventoy USB Factory Design

Date: 2026-08-19
Status: Draft approved for planning after user review

## Goal

Build a local tool that prepares multiple USB drives in parallel with Ventoy and copies bootable ISO files for Windows 10, Windows 11, and Ubuntu.

The first supported platform is Ubuntu. The architecture should avoid blocking future support for macOS and Windows, but direct disk writing on those systems is not part of the first implementation.

## Product Scope

The tool runs locally on the operator's computer and exposes a browser-based management interface on `localhost`.

The operator can:

- See all connected removable USB storage devices.
- Select one or more USB drives to prepare.
- Confirm destructive operations per selected drive.
- Install Ventoy on selected drives.
- Copy ISO files to the Ventoy data partition.
- Track per-drive progress, status, and errors.
- Use local ISO files when available.
- Let the tool attempt to fetch missing ISO files for Windows 10, Windows 11, and Ubuntu.

## Non-Goals For MVP

- Full macOS or Windows disk-writing support.
- Guaranteed automatic Windows ISO downloads in every region or language.
- Bypassing Microsoft licensing, download gates, authentication, or terms.
- Automatically preparing every connected USB drive without operator selection.
- Running primarily inside Docker.
- Network multi-user management.

## Primary Platform

Ubuntu is the priority target.

The backend may require elevated privileges because Ventoy installation and partition handling need raw block-device access. The intended startup mode is a local command run with `sudo`, for example a future command similar to:

```bash
sudo ventoy-usb-factory
```

The web UI binds only to localhost by default.

## Architecture

The system is split into four main parts:

- Web UI: browser interface for device selection, confirmations, ISO status, and job progress.
- Local backend API: owns device discovery, safety checks, job orchestration, and logs.
- Device worker layer: performs Ventoy installation, partition detection, mounting, and file copy operations.
- ISO manager: resolves local ISO files first, then attempts controlled downloads for missing ISO files.

Implementation stack for MVP:

- Backend: Python with FastAPI.
- Frontend: server-rendered HTML with small progressive JavaScript where needed.
- Process execution: backend invokes trusted system tools such as `lsblk`, `udevadm`, `mount`, `umount`, `rsync` or equivalent copy operations, and the official Ventoy installer script/binary.

The implementation should prefer a small backend with explicit command wrappers over a large abstraction layer.

## Device Discovery

On Ubuntu, device detection uses block-device metadata from `lsblk` and `udevadm`.

Each device record shown in the UI includes:

- Device path, for example `/dev/sdb`.
- Model/vendor when available.
- Size.
- Removable flag.
- Mountpoints for existing partitions.
- Filesystem labels.
- Safety classification.

The backend must exclude obvious system disks. A device is not eligible if it contains `/`, `/boot`, `/home`, or other active system mountpoints, or if it is not a removable USB-style storage device unless the operator explicitly enables a future unsafe override.

The MVP should not include an unsafe override.

## Safety Model

Installing Ventoy is destructive. Safety is a core requirement.

The tool must:

- Never auto-select drives.
- Require the operator to select devices manually.
- Require explicit confirmation for each selected device before installation.
- Display path, model, and size during confirmation.
- Re-scan devices immediately before starting each destructive operation.
- Refuse to operate if the device changed identity, disappeared, or became mounted as a system path.
- Log every destructive command before and after execution.
- Avoid shell string interpolation for device paths; use argument arrays when spawning commands.

The UI copy should clearly say that all existing data on selected USB drives will be erased.

## Job Flow

For each selected USB drive:

1. Revalidate the device.
2. Unmount any mounted partitions belonging to the device.
3. Run the Ventoy installer for that device.
4. Wait for the OS to detect the new Ventoy partitions.
5. Mount the Ventoy data partition.
6. Copy selected ISO files to the data partition.
7. Sync filesystem buffers.
8. Unmount the partition.
9. Mark the drive complete or failed.

Multiple drives can be processed in parallel. The initial parallelism should be configurable and conservative, with a default maximum of two concurrent drive jobs to reduce USB bus contention and confusing failures.

## ISO Management

The ISO manager supports a hybrid mode.

Local ISO files are preferred. During development, the MVP uses a project-local `./isos` directory. A later installed package can default to `/var/lib/ventoy-usb-factory/isos`.

For each required OS, the ISO manager tracks:

- Name: Windows 10, Windows 11, Ubuntu.
- Source type: local file or downloaded file.
- Version or release label when detectable.
- File size.
- Checksum status when available.
- Readiness status.

Ubuntu downloads use the latest Ubuntu LTS desktop ISO from official Ubuntu release URLs and checksum files.

Windows downloads should use official Microsoft URLs when stable direct links are available. If automatic resolution fails, the UI should show a clear manual action: download the ISO from Microsoft and place it in the configured ISO folder. The tool must not scrape around licensing gates or use unofficial mirrors by default.

## UI Design

The UI is functional and safety-oriented.

Main screens:

- Dashboard: device list, ISO readiness, active jobs.
- Device selection: eligible USB drives with details and warnings.
- Confirmation: one confirmation card per selected drive.
- Progress: per-drive stage, percentage when known, live logs, success/failure state.
- Settings: ISO directory, concurrency limit, Ventoy installer location.

The UI should be responsive enough for desktop and laptop screens. Mobile support is useful but not a primary workflow because the tool operates on local USB hardware.

## Backend API Shape

Initial API endpoints:

- `GET /api/devices`: list detected USB storage devices and safety status.
- `GET /api/isos`: list required ISO readiness and source status.
- `POST /api/isos/refresh`: rescan local ISO directory and retry metadata/download checks.
- `POST /api/jobs`: create a preparation job for selected devices and ISO set.
- `GET /api/jobs`: list jobs.
- `GET /api/jobs/{id}`: job details.
- `GET /api/jobs/{id}/events`: stream progress events using Server-Sent Events or WebSocket.

The MVP can use Server-Sent Events for progress because the UI mostly receives updates and does not need bidirectional real-time control.

## Data Storage

The MVP can keep active job state in memory and write logs to disk.

Recommended local paths:

- Development config: `./config.yaml`.
- Development ISO cache: `./isos`.
- Development logs: `./logs`.
- Installed config: `/etc/ventoy-usb-factory/config.yaml`.
- Installed ISO cache: `/var/lib/ventoy-usb-factory/isos`.
- Installed logs: `/var/log/ventoy-usb-factory/`.

If a database becomes necessary later, SQLite is enough.

## Error Handling

Errors must be attached to the specific drive job whenever possible.

Common failure cases:

- Device removed during operation.
- Device identity changed after confirmation.
- Mount or unmount failed.
- Ventoy installer failed.
- Ventoy partition did not appear.
- Not enough space for ISO files.
- ISO download failed.
- ISO checksum failed.
- Copy interrupted.

The UI should make partial success clear: one drive can fail while another succeeds.

## Security Considerations

The backend runs with elevated privileges, so the HTTP server must bind to `127.0.0.1` by default.

No remote access is part of the MVP.

The backend must validate all device paths against its latest discovered device list. The API must never accept arbitrary command strings or arbitrary device paths without validation.

Logs should not contain secrets. The MVP should not require cloud credentials.

## Docker Position

Docker is not the primary runtime because raw USB/block-device access is unreliable across platforms and requires privileged containers on Linux.

A later Linux-only Docker mode can be documented for advanced users, likely requiring:

```bash
docker run --privileged -v /dev:/dev ...
```

This mode is explicitly lower priority than the native Ubuntu local server.

## Future Platform Support

macOS and Windows can be explored later through platform-specific device discovery and privileged disk-writing mechanisms.

The backend should isolate platform-specific code behind small interfaces:

- Device discovery.
- Mount/unmount operations.
- Ventoy installation command execution.
- Filesystem sync/eject operations.

The MVP only implements the Linux backend.

## Testing Strategy

Unit tests:

- Parse `lsblk` output.
- Classify safe vs unsafe devices.
- Validate job creation rules.
- Resolve local ISO metadata.
- Handle downloader success/failure states.

Integration tests:

- Mock command runner for Ventoy, mount, unmount, and copy commands.
- Simulate multiple parallel jobs.
- Simulate device disappearance and identity mismatch.

Manual hardware tests:

- One USB drive happy path.
- Two USB drives in parallel.
- Device removed before install.
- Device removed during copy.
- Existing mounted partitions.
- Missing Windows ISO with manual fallback.

Real destructive tests must only run when explicitly enabled by the tester.

## MVP Acceptance Criteria

The MVP is successful when, on Ubuntu:

- The app starts locally and opens a web UI.
- The UI lists connected removable USB drives with model, size, and path.
- System disks are excluded from preparation.
- The user can select multiple USB drives.
- The user must confirm each selected drive before install.
- The backend installs Ventoy on each confirmed drive.
- The backend copies available Windows 10, Windows 11, and Ubuntu ISO files to each drive.
- The UI shows per-drive progress and final status.
- Failures on one drive do not stop unrelated drive jobs unless shared prerequisites fail.

## Implementation Decisions

- Backend language: Python.
- Backend framework: FastAPI.
- Frontend style: server-rendered HTML with minimal JavaScript.
- Ventoy installer: configured path to an official Ventoy release extracted locally by the operator or setup script; vendoring Ventoy binaries is not part of the MVP.
- Development ISO directory: `./isos`.
- Installed ISO directory: `/var/lib/ventoy-usb-factory/isos`.
- Default Ubuntu release target: latest LTS desktop ISO.
