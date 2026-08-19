import pytest

from ventoy_usb_factory.commands import CommandResult


class FakeCommandRunner:
    def __init__(self, results: list[CommandResult]):
        self.results = list(results)
        self.calls: list[list[str]] = []

    def run(self, args: list[str], timeout: int | None = None) -> CommandResult:
        self.calls.append(args)
        if not self.results:
            raise AssertionError(f"No fake result configured for {args}")
        return self.results.pop(0)


@pytest.fixture
def command_result():
    def factory(args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0):
        return CommandResult(args=args, stdout=stdout, stderr=stderr, returncode=returncode)

    return factory
