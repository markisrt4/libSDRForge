# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Optional redsea streaming RDS adapter.

redsea consumes 240 kHz mono S16LE FM multiplex through stdin and emits
newline-delimited JSON on stdout. Partial groups are retained for diagnostics
but never promoted to validated RDS groups.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import queue
import subprocess
import threading
from typing import Any, BinaryIO

import numpy as np

from sdrforge.protocols.rds.rds_block_sync import RdsGroup


@dataclass(frozen=True)
class RedseaRecord:
    payload: dict[str, Any]
    group: RdsGroup | None


def parse_redsea_line(line: str) -> RedseaRecord | None:
    """Parse one JSON line, rejecting incomplete groups as validated data."""
    try:
        value = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    raw = value.get("raw_data")
    if not isinstance(raw, str):
        return RedseaRecord(value, None)
    words = raw.split()
    if len(words) != 4 or any(len(word) != 4 for word in words):
        return RedseaRecord(value, None)
    if any(word == "----" for word in words):
        return RedseaRecord(value, None)
    try:
        a, b, c, d = (int(word, 16) for word in words)
    except ValueError:
        return RedseaRecord(value, None)
    if any(word > 0xFFFF for word in (a, b, c, d)):
        return RedseaRecord(value, None)
    kind = f"{(b >> 12) & 0xF}{'B' if b & 0x0800 else 'A'}"
    if value.get("group") != kind:
        return RedseaRecord(value, None)
    # redsea may have corrected bits using FEC. Provenance is not available
    # in its JSON group records; do not label these as native strict groups.
    group = RdsGroup(a, b, c, d, bool(b & 0x0800),
                     synchronization="redsea_fec_unknown")
    return RedseaRecord(value, group)


def multiplex_to_pcm(multiplex: np.ndarray, *, amplitude: float = 0.2) -> bytes:
    """Convert 240 kHz discriminator output to signed little-endian PCM16."""
    if not 0 < amplitude <= 1:
        raise ValueError("amplitude must be in (0, 1]")
    values = np.asarray(multiplex)
    if values.ndim != 1 or not np.issubdtype(values.dtype, np.number):
        raise ValueError("expected one-dimensional numeric multiplex samples")
    if not np.all(np.isfinite(values)):
        raise ValueError("multiplex contains nonfinite samples")
    return (np.clip(values.astype(np.float64) * amplitude, -1, 1)
            * 32767).astype("<i2").tobytes()


class RedseaRdsAdapter:
    """Manage a redsea process without coupling it to the WBFM receiver.

    The background reader prevents stdout pipe deadlocks. `drain()` returns
    records decoded since the previous drain; a caller can feed complete
    records into metadata and TMC consumers. Not safe for concurrent writes.
    """

    def __init__(self, *, executable: str = "redsea", amplitude: float = 0.2,
                 samplerate_hz: int = 240_000, queue_capacity: int = 32) -> None:
        if samplerate_hz <= 0:
            raise ValueError("sample rate must be positive")
        if not 0 < amplitude <= 1:
            raise ValueError("amplitude must be in (0, 1]")
        if queue_capacity < 1:
            raise ValueError("queue capacity must be positive")
        self._input: queue.Queue[bytes | None] = queue.Queue(maxsize=queue_capacity)
        self.dropped_blocks = 0
        self._writer: threading.Thread | None = None
        self._writer_error: str | None = None
        self.executable = executable
        self.amplitude = amplitude
        self.samplerate_hz = samplerate_hz
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pending: list[RedseaRecord] = []

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("redsea already started")
        self._process = subprocess.Popen(
            [self.executable, "--input", "mpx", "--samplerate",
             str(self.samplerate_hz), "--output", "json", "--show-raw",
             "--show-partial"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0,
        )
        assert self._process.stdout is not None
        self._reader = threading.Thread(
            target=self._read_output, args=(self._process.stdout,),
            name="redsea-json-reader", daemon=True,
        )
        self._reader.start()
        self._writer = threading.Thread(target=self._write_input,
                                        name="redsea-pcm-writer", daemon=True)
        self._writer.start()

    def _read_output(self, stdout: BinaryIO) -> None:
        for line in stdout:
            record = parse_redsea_line(line.decode("utf-8", errors="replace"))
            if record is not None:
                with self._lock:
                    self._pending.append(record)

    def _write_input(self) -> None:
        proc = self._process
        if proc is None or proc.stdin is None:
            return
        try:
            while True:
                data = self._input.get()
                if data is None:
                    break
                proc.stdin.write(data)
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._writer_error = str(exc)

    def feed(self, multiplex: np.ndarray) -> bool:
        """Queue multiplex samples without blocking the caller.

        Returns False when the bounded queue is full; the newest block is
        dropped to avoid delaying live audio.
        """
        proc = self._process
        if proc is None:
            raise RuntimeError("redsea not started")
        if self._writer_error is not None:
            raise RuntimeError(f"redsea writer failed: {self._writer_error}")
        if proc.poll() is not None:
            raise RuntimeError(f"redsea exited with code {proc.returncode}")
        data = multiplex_to_pcm(multiplex, amplitude=self.amplitude)
        try:
            self._input.put_nowait(data)
        except queue.Full:
            self.dropped_blocks += 1
            return False
        return True

    def drain(self) -> tuple[RedseaRecord, ...]:
        with self._lock:
            records = tuple(self._pending)
            self._pending.clear()
        return records

    def close(self) -> None:
        proc = self._process
        if proc is None:
            return
        if self._writer is not None:
            try:
                self._input.put_nowait(None)
            except queue.Full:
                pass
            self._writer.join(timeout=2)
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
        if self._reader is not None:
            self._reader.join(timeout=2)
        self._process = None
        self._reader = None
        self._writer = None

    def __enter__(self) -> "RedseaRdsAdapter":
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
