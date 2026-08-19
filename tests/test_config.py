from pathlib import Path

from ventoy_usb_factory.config import load_config


def test_load_config_uses_safe_development_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    config = load_config(None)

    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.iso_dir == tmp_path / "isos"
    assert config.log_dir == tmp_path / "logs"
    assert config.ventoy_installer == tmp_path / "ventoy" / "Ventoy2Disk.sh"
    assert config.max_concurrent_jobs == 2


def test_load_config_reads_yaml_values(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "host: 127.0.0.1\n"
        "port: 9090\n"
        "iso_dir: /tmp/custom-isos\n"
        "log_dir: /tmp/custom-logs\n"
        "ventoy_installer: /opt/ventoy/Ventoy2Disk.sh\n"
        "max_concurrent_jobs: 1\n",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.port == 9090
    assert config.iso_dir == Path("/tmp/custom-isos")
    assert config.log_dir == Path("/tmp/custom-logs")
    assert config.ventoy_installer == Path("/opt/ventoy/Ventoy2Disk.sh")
    assert config.max_concurrent_jobs == 1
