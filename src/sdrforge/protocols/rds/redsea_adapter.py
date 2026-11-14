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
from pathlib import Path
import subprocess
import threading
from typing import Any, BinaryIO, TextIO

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
                 samplerate_hz: int = 240_000) -> None:
        if samplerate_hz <= 0:
            raise ValueError("sample rate must be positive")
        if not 0 < amplitude <= 1:
            raise ValueError("amplitude must be in (0, 1]")
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

    def _read_output(self, stdout: BinaryIO) -> None:
        for line in stdout:
            record = parse_redsea_line(line.decode("utf-8", errors="replace"))
            if record is not None:
                with self._lock:
                    self._pending.append(record)

    def feed(self, multiplex: np.ndarray) -> None:
        proc = self._process
        if proc is None or proc.stdin is None:
            raise RuntimeError("redsea not started")
        if proc.poll() is not None:
            raise RuntimeError(f"redsea exited with code {proc.returncode}")
        data = multiplex_to_pcm(multiplex, amplitude=self.amplitude)
        try:
            proc.stdin.write(data)
        except BrokenPipeError as exc:
            raise RuntimeError("redsea input pipe closed") from exc

    def drain(self) -> tuple[RedseaRecord, ...]:
        with self._lock:
            records = tuple(self._pending)
            self._pending.clear()
        return records

    def close(self) -> None:
        proc = self._process
        if proc is None:
            return
        self._process = None
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if self._reader is not None:
            self._reader.join(timeout=2)
            self._reader = None

    def __enter__(self) -> "RedseaRdsAdapter":
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
