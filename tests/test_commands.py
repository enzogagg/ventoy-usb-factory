import subprocess

from ventoy_usb_factory.commands import SubprocessCommandRunner


def test_subprocess_command_runner_uses_safe_subprocess_options(monkeypatch):
    calls = []

    class FakeStream:
        def readline(self):
            return ""

    class FakeProcess:
        stdout = FakeStream()
        stderr = FakeStream()
        stdin = None
        returncode = 0

        def wait(self, timeout=None):
            return self.returncode

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = SubprocessCommandRunner().run(["lsblk", "--json"], timeout=5)

    assert calls == [
        (
            (["lsblk", "--json"],),
            {
                "shell": False,
                "text": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "stdin": None,
            },
        )
    ]
    assert result.args == ["lsblk", "--json"]
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_subprocess_command_runner_streams_stdout_and_stderr(monkeypatch):
    events = []

    class FakeStream:
        def __init__(self, lines):
            self._lines = iter(lines)

        def readline(self):
            return next(self._lines, "")

    class FakeProcess:
        def __init__(self):
            self.stdout = FakeStream(["out 1\n", "out 2\n"])
            self.stderr = FakeStream(["err 1\n"])
            self.stdin = None
            self.returncode = 0

        def wait(self, timeout=None):
            assert timeout == 10
            return self.returncode

    def fake_popen(*args, **kwargs):
        events.append(("popen", args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = SubprocessCommandRunner().run(
        ["ventoy"], timeout=10, on_output=lambda stream, line: events.append((stream, line))
    )

    assert events[0] == (
        "popen",
        (["ventoy"],),
        {
            "shell": False,
            "text": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": None,
        },
    )
    assert ("stdout", "out 1") in events
    assert ("stdout", "out 2") in events
    assert ("stderr", "err 1") in events
    assert result.stdout == "out 1\nout 2\n"
    assert result.stderr == "err 1\n"


def test_subprocess_command_runner_sends_input_text_to_stdin(monkeypatch):
    writes = []

    class FakeStream:
        def readline(self):
            return ""

    class FakeStdin:
        def write(self, value):
            writes.append(("write", value))

        def close(self):
            writes.append(("close", None))

    class FakeProcess:
        stdout = FakeStream()
        stderr = FakeStream()
        stdin = FakeStdin()
        returncode = 0

        def wait(self, timeout=None):
            return self.returncode

    def fake_popen(*args, **kwargs):
        writes.append(("popen", kwargs["stdin"]))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    SubprocessCommandRunner().run(["ventoy"], input_text="y\ny\n")

    assert writes == [("popen", subprocess.PIPE), ("write", "y\ny\n"), ("close", None)]
