import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Thread
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(
        self,
        args: list[str],
        timeout: int | None = None,
        on_output: Callable[[str, str], None] | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        raise NotImplementedError


class SubprocessCommandRunner:
    def run(
        self,
        args: list[str],
        timeout: int | None = None,
        on_output: Callable[[str, str], None] | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        process = subprocess.Popen(
            args,
            shell=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if input_text is not None else None,
        )
        if process.stdin is not None and input_text is not None:
            process.stdin.write(input_text)
            process.stdin.close()
        output_queue: Queue[tuple[str, str | None]] = Queue()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def read_stream(stream_name: str) -> None:
            stream = getattr(process, stream_name)
            if stream is None:
                output_queue.put((stream_name, None))
                return
            while True:
                line = stream.readline()
                if line == "":
                    break
                output_queue.put((stream_name, line))
            output_queue.put((stream_name, None))

        readers = [
            Thread(target=read_stream, args=("stdout",), daemon=True),
            Thread(target=read_stream, args=("stderr",), daemon=True),
        ]
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + timeout if timeout is not None else None
        closed_streams = 0
        while closed_streams < 2:
            queue_timeout = 0.1
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    raise subprocess.TimeoutExpired(args, timeout)
                queue_timeout = min(queue_timeout, remaining)
            try:
                stream_name, line = output_queue.get(timeout=queue_timeout)
            except Empty:
                continue
            if line is None:
                closed_streams += 1
                continue
            if stream_name == "stdout":
                stdout_lines.append(line)
            else:
                stderr_lines.append(line)
            if on_output:
                on_output(stream_name, line.rstrip("\n"))

        for reader in readers:
            reader.join(timeout=1)

        returncode = process.wait(timeout=timeout)

        return CommandResult(
            args=args,
            returncode=returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
        )
