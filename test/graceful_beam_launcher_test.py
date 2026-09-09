#!/usr/bin/env python3
"""Black-box pseudo-TTY and process-group tests for the BEAM shutdown launcher."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

LAUNCHER = Path(__file__).parents[1] / "bin" / "graceful-beam-launcher"


def parse_events(stderr: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stderr.splitlines():
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise AssertionError(f"invalid JSON log line: {line!r}") from error
    return events


def names(events: list[dict[str, Any]]) -> list[str]:
    return [str(event.get("event")) for event in events]


def start_with_tty(
    command: str = 'trap "" TERM; while :; do sleep 1; done',
    grace_ms: str = "1000",
) -> tuple[subprocess.Popen[str], int]:
    master, slave = os.openpty()
    process = subprocess.Popen(
        ["bash", str(LAUNCHER), "bash", "-c", command],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
        env={**os.environ, "SHUTDOWN_GRACE_MS": grace_ms},
    )
    os.close(slave)
    return process, master


def finish(process: subprocess.Popen[str], timeout: float = 6.0) -> tuple[int, str]:
    try:
        _, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        _, stderr = process.communicate(timeout=2)
        raise AssertionError(f"launcher did not exit; stderr:\n{stderr}")
    return process.returncode, stderr


def assert_non_tty_sigterm() -> None:
    process = subprocess.Popen(
        [
            "bash",
            str(LAUNCHER),
            "bash",
            "-c",
            'trap "exit 0" TERM; while :; do sleep 1; done',
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "SHUTDOWN_GRACE_MS": "1000"},
    )
    time.sleep(0.20)
    os.kill(process.pid, signal.SIGTERM)
    returncode, stderr = finish(process)
    events = parse_events(stderr)
    if returncode != 0 or names(events) != [
        "shutdown_requested",
        "shutdown_complete",
    ]:
        raise AssertionError(f"non-TTY graceful mismatch:\n{stderr}")
    if (
        events[0].get("stdin_is_tty") is not False
        or events[0].get("signal_count") != 1
    ):
        raise AssertionError(f"non-TTY fields mismatch: {events!r}")


def assert_tty_sigterm_does_not_arm_eof() -> None:
    process, master = start_with_tty(
        'trap "exit 0" TERM; while :; do sleep 1; done'
    )
    try:
        time.sleep(0.20)
        os.kill(process.pid, signal.SIGTERM)
        returncode, stderr = finish(process)
    finally:
        os.close(master)
    events = parse_events(stderr)
    if returncode != 0 or names(events) != [
        "shutdown_requested",
        "shutdown_complete",
    ]:
        raise AssertionError(f"TTY SIGTERM mismatch:\n{stderr}")
    if events[0].get("signal_count") != 1 or any(
        event.get("event") == "shutdown_force_available" for event in events
    ):
        raise AssertionError(f"TTY SIGTERM armed interactive EOF: {events!r}")


def assert_tty_second_sigint() -> None:
    process, master = start_with_tty()
    try:
        time.sleep(0.20)
        os.kill(process.pid, signal.SIGINT)
        time.sleep(0.20)
        os.kill(process.pid, signal.SIGINT)
        returncode, stderr = finish(process)
    finally:
        os.close(master)

    events = parse_events(stderr)
    expected = [
        "shutdown_requested",
        "shutdown_force_available",
        "shutdown_forced",
        "shutdown_complete",
    ]
    if names(events) != expected:
        raise AssertionError(f"second-SIGINT events {names(events)!r} != {expected!r}\n{stderr}")
    if returncode != 137:
        raise AssertionError(f"forced child exit status was {returncode}, expected 137")
    if events[2].get("trigger") != "sigint" or events[2].get("signal_count") != 2:
        raise AssertionError(f"second SIGINT contract mismatch: {events[2]!r}")


def assert_tty_eof() -> None:
    process, master = start_with_tty()
    time.sleep(0.20)
    os.kill(process.pid, signal.SIGINT)
    time.sleep(0.20)
    os.close(master)
    returncode, stderr = finish(process)

    events = parse_events(stderr)
    expected = [
        "shutdown_requested",
        "shutdown_force_available",
        "shutdown_forced",
        "shutdown_complete",
    ]
    if names(events) != expected:
        raise AssertionError(f"TTY EOF events {names(events)!r} != {expected!r}\n{stderr}")
    if returncode != 137:
        raise AssertionError(f"EOF-forced child exit status was {returncode}, expected 137")
    if events[2].get("trigger") != "stdin_eof" or events[2].get("signal_count") != 1:
        raise AssertionError(f"TTY EOF contract mismatch: {events[2]!r}")


def assert_second_sigterm_forces() -> None:
    process = subprocess.Popen(
        ["bash", str(LAUNCHER), "bash", "-c", 'trap "" TERM; while :; do sleep 1; done'],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "SHUTDOWN_GRACE_MS": "2000"},
    )
    time.sleep(0.20)
    os.kill(process.pid, signal.SIGTERM)
    time.sleep(0.15)
    os.kill(process.pid, signal.SIGTERM)
    returncode, stderr = finish(process)
    events = parse_events(stderr)
    expected = ["shutdown_requested", "shutdown_forced", "shutdown_complete"]
    if names(events) != expected:
        raise AssertionError(f"second-SIGTERM events {names(events)!r} != {expected!r}\n{stderr}")
    if returncode != 137:
        raise AssertionError(f"second-SIGTERM exit status was {returncode}, expected 137")
    if events[1].get("trigger") != "sigterm" or events[1].get("signal_count") != 2:
        raise AssertionError(f"second SIGTERM contract mismatch: {events[1]!r}")


def assert_timeout_forces() -> None:
    process = subprocess.Popen(
        ["bash", str(LAUNCHER), "bash", "-c", 'trap "" TERM; while :; do sleep 1; done'],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "SHUTDOWN_GRACE_MS": "250"},
    )
    time.sleep(0.20)
    started = time.monotonic()
    os.kill(process.pid, signal.SIGTERM)
    returncode, stderr = finish(process)
    elapsed = time.monotonic() - started
    events = parse_events(stderr)
    expected = ["shutdown_requested", "shutdown_forced", "shutdown_complete"]
    if names(events) != expected:
        raise AssertionError(f"timeout events {names(events)!r} != {expected!r}\n{stderr}")
    if events[1].get("trigger") != "timeout" or events[1].get("forced") is not True:
        raise AssertionError(f"timeout force contract mismatch: {events[1]!r}")
    if returncode != 137:
        raise AssertionError(f"timeout-forced exit status was {returncode}, expected 137")
    if elapsed < 0.20 or elapsed > 2.0:
        raise AssertionError(f"timeout force elapsed {elapsed:.3f}s outside bounded range")


def pid_is_running(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return False
    try:
        fields = stat.read_text().split()
    except FileNotFoundError:
        return False
    return len(fields) > 2 and fields[2] != "Z"


def assert_force_kills_descendant_group() -> None:
    with tempfile.TemporaryDirectory(prefix="beam-launcher-") as td:
        pid_file = Path(td) / "descendant.pid"
        command = (
            'trap "" TERM; '
            '(trap "" TERM; while :; do sleep 1; done) & '
            f'echo $! > {pid_file!s}; '
            'wait'
        )
        process = subprocess.Popen(
            ["bash", str(LAUNCHER), "bash", "-c", command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "SHUTDOWN_GRACE_MS": "2000"},
        )
        deadline = time.monotonic() + 2.0
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not pid_file.exists():
            process.kill()
            raise AssertionError("descendant PID was not published")
        descendant_pid = int(pid_file.read_text().strip())
        if not pid_is_running(descendant_pid):
            process.kill()
            raise AssertionError("descendant was not running before shutdown")

        os.kill(process.pid, signal.SIGTERM)
        time.sleep(0.15)
        os.kill(process.pid, signal.SIGTERM)
        returncode, stderr = finish(process)
        if returncode != 137:
            raise AssertionError(f"process-group force exit status was {returncode}, expected 137")

        deadline = time.monotonic() + 2.0
        while pid_is_running(descendant_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        if pid_is_running(descendant_pid):
            raise AssertionError(f"descendant {descendant_pid} survived process-group SIGKILL\n{stderr}")


def assert_invalid_grace_fails_closed() -> None:
    process = subprocess.run(
        ["bash", str(LAUNCHER), "true"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "SHUTDOWN_GRACE_MS": "0"},
        timeout=2,
        check=False,
    )
    if process.returncode != 64:
        raise AssertionError(f"invalid grace returned {process.returncode}, expected 64")
    events = parse_events(process.stderr)
    if len(events) != 1 or events[0].get("event") != "shutdown_config_invalid":
        raise AssertionError(f"invalid grace did not fail closed: {process.stderr!r}")


def main() -> int:
    if not LAUNCHER.is_file():
        raise AssertionError(f"launcher not found: {LAUNCHER}")
    assert_invalid_grace_fails_closed()
    assert_non_tty_sigterm()
    assert_tty_sigterm_does_not_arm_eof()
    assert_tty_second_sigint()
    assert_tty_eof()
    assert_second_sigterm_forces()
    assert_timeout_forces()
    assert_force_kills_descendant_group()
    print("BEAM launcher shutdown contract passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
