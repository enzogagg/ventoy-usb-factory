import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: list[str], timeout: int | None = None) -> CommandResult:
        raise NotImplementedError


class SubprocessCommandRunner:
    def run(self, args: list[str], timeout: int | None = None) -> CommandResult:
        completed = subprocess.run(
            args,
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
