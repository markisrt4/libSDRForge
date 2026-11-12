# SPDX-License-Identifier: MIT
"""Small localhost RigCTL-compatible TCP server for a libSDRForge receiver.

The receiver is injected so the protocol can be tested without SDR hardware.
"""
from __future__ import annotations

import socketserver
from typing import Protocol


class ReceiverControl(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def set_frequency(self, hz: int) -> None: ...
    def get_frequency(self) -> int: ...
    def set_mode(self, mode: str, bandwidth: int) -> None: ...
    def get_mode(self) -> tuple[str, int]: ...
    def get_signal_strength(self) -> float | None: ...
    def get_snr(self) -> float | None: ...
    def get_rds(self) -> str | None: ...


class RigctlServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, receiver: ReceiverControl, host: str = "127.0.0.1",
                 port: int = 4532) -> None:
        self.receiver = receiver
        super().__init__((host, port), RigctlHandler)


class RigctlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        # ORC currently uses one command per TCP connection.
        for raw in self.rfile:
            command = raw.decode("utf-8", errors="replace").strip()
            if not command:
                continue
            try:
                response = self.dispatch(command)
            except (ValueError, RuntimeError, OSError):
                response = "RPRT -1"
            self.wfile.write((response + "\n").encode("utf-8"))
            self.wfile.flush()

    def dispatch(self, command: str) -> str:
        receiver = self.server.receiver
        parts = command.split()
        op = parts[0]
        if op == "f" and len(parts) == 1:
            return str(receiver.get_frequency())
        if op == "F" and len(parts) == 2:
            frequency = int(parts[1])
            if frequency <= 0:
                raise ValueError("invalid frequency")
            receiver.set_frequency(frequency)
            return "RPRT 0"
        if op == "M" and len(parts) == 3:
            mode = parts[1].upper()
            if mode not in {"FM", "NFM", "WFM", "AM"}:
                raise ValueError("unsupported mode")
            bandwidth = int(parts[2])
            if bandwidth < 0:
                raise ValueError("invalid bandwidth")
            receiver.set_mode(mode, bandwidth)
            return "RPRT 0"
        if op == "m" and len(parts) == 1:
            mode, bandwidth = receiver.get_mode()
            return f"{mode}\\n{bandwidth}"
        if op == r"\start" and len(parts) == 1:
            receiver.start()
            return "RPRT 0"
        if op == r"\stop" and len(parts) == 1:
            receiver.stop()
            return "RPRT 0"
        if op == "l" and len(parts) == 2:
            key = parts[1].upper()
            if key == "STRENGTH":
                value = receiver.get_signal_strength()
            elif key == "SNR":
                value = receiver.get_snr()
            elif key == "RDS":
                value = receiver.get_rds()
            else:
                return "RPRT -4"
            return str(value) if value is not None else ""
        return "RPRT -4"
