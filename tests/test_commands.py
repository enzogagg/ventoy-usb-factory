import subprocess

from ventoy_usb_factory.commands import SubprocessCommandRunner


def test_subprocess_command_runner_uses_safe_subprocess_options(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = SubprocessCommandRunner().run(["lsblk", "--json"], timeout=5)

    assert calls == [
        (
            (["lsblk", "--json"],),
            {
                "shell": False,
                "text": True,
                "capture_output": True,
                "timeout": 5,
                "check": False,
            },
        )
    ]
    assert result.args == ["lsblk", "--json"]
    assert result.returncode == 0
    assert result.stdout == "out"
    assert result.stderr == "err"
