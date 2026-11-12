# SPDX-License-Identifier: MIT
"""RigCTL command interpreter, independent of TCP sockets."""
from __future__ import annotations

from sdrforge.interfaces.receiver_control import ReceiverControlIf


class RigctlCommandHandler:
    def __init__(self, receiver: ReceiverControlIf) -> None:
        self.receiver = receiver

    def dispatch(self, command: str) -> str:
        receiver = self.receiver
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
            return f"{mode}\n{bandwidth}"
        if op == r"\start" and len(parts) == 1:
            receiver.start()
            return "RPRT 0"
        if op == r"\stop" and len(parts) == 1:
            receiver.stop()
            return "RPRT 0"
        if op == "l" and len(parts) == 2:
            key = parts[1].upper()
            value: float | str | None
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
