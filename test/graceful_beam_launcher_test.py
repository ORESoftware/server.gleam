#!/usr/bin/env python3
"""Black-box pseudo-TTY tests for the BEAM shutdown launcher."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
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
) -> tuple[subprocess.Popen[str], int]:
    master, slave = os.openpty()
    process = subprocess.Popen(
        ["bash", str(LAUNCHER), "bash", "-c", command],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
        env={**os.environ, "SHUTDOWN_GRACE_MS": "1000"},
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
        _, stderr = finish(process)
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
    if events[2].get("trigger") != "sigint" or events[2].get("signal_count") != 2:
        raise AssertionError(f"second SIGINT contract mismatch: {events[2]!r}")


def assert_tty_eof() -> None:
    process, master = start_with_tty()
    time.sleep(0.20)
    os.kill(process.pid, signal.SIGINT)
    time.sleep(0.20)
    os.close(master)
    _, stderr = finish(process)

    events = parse_events(stderr)
    expected = [
        "shutdown_requested",
        "shutdown_force_available",
        "shutdown_forced",
        "shutdown_complete",
    ]
    if names(events) != expected:
        raise AssertionError(f"TTY EOF events {names(events)!r} != {expected!r}\n{stderr}")
    if events[2].get("trigger") != "stdin_eof" or events[2].get("signal_count") != 1:
        raise AssertionError(f"TTY EOF contract mismatch: {events[2]!r}")


def main() -> int:
    if not LAUNCHER.is_file():
        raise AssertionError(f"launcher not found: {LAUNCHER}")
    assert_non_tty_sigterm()
    assert_tty_sigterm_does_not_arm_eof()
    assert_tty_second_sigint()
    assert_tty_eof()
    print("BEAM launcher shutdown contract passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
