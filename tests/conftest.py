import pytest

from ventoy_usb_factory.commands import CommandResult


class FakeCommandRunner:
    def __init__(self, results: list[CommandResult]):
        self.results = list(results)
        self.calls: list[list[str]] = []
        self.inputs: list[str | None] = []

    def run(
        self,
        args: list[str],
        timeout: int | None = None,
        on_output=None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(args)
        self.inputs.append(input_text)
        if not self.results:
            raise AssertionError(f"No fake result configured for {args}")
        result = self.results.pop(0)
        if on_output:
            for line in result.stdout.splitlines():
                on_output("stdout", line)
            for line in result.stderr.splitlines():
                on_output("stderr", line)
        return result


@pytest.fixture
def command_result():
    def factory(args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0):
        return CommandResult(args=args, stdout=stdout, stderr=stderr, returncode=returncode)

    return factory
