# Ventoy USB Factory

Local Ubuntu-first tool for preparing USB drives with Ventoy and bootable ISO files.

WARNING: Installing Ventoy erases the selected USB drive. Verify the device path, model, and size before confirming.

## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp config.example.yaml config.yaml
```

The `ventoy-usb-factory` CLI and web app entry point will be implemented in a later task.

## Configuration

Copy `config.example.yaml` to `config.yaml` and adjust local paths as needed.

## Safety

This project is designed for local use and binds to `127.0.0.1` by default.
