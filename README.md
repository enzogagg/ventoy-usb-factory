# Ventoy USB Factory

Local Ubuntu-first tool for preparing USB drives with Ventoy and bootable ISO files.

## Development Setup

```bash
uv python pin 3.12.7
uv sync --extra dev
cp config.example.yaml config.yaml
uv run ventoy-usb-factory
```

The web UI binds to `127.0.0.1` by default for local operation.

On Ubuntu, real Ventoy installation requires root privileges:

```bash
sudo env "PATH=$PATH" uv run ventoy-usb-factory
```

## Ventoy Setup

Download the official Ventoy Linux release from https://www.ventoy.net/ and extract it to `./ventoy` so `./ventoy/Ventoy2Disk.sh` exists.

## ISO Folder

Place local ISO files in `./isos`. File names should include `Win10`, `Win11`, or `ubuntu` so the scanner can classify them.

## Configuration

Copy `config.example.yaml` to `config.yaml` and adjust local paths as needed.

## Safety

WARNING: Installing Ventoy erases the selected USB drive. Verify the device path, model, and size before confirming.

This tool is destructive. It never auto-selects USB drives. Each selected drive requires a browser confirmation popup before preparation starts.

No hardware test should be run by default. Real destructive tests require explicit tester consent and disposable USB drives.
