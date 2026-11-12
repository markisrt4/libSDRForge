# SPDX-License-Identifier: MIT
"""Small localhost RigCTL-compatible TCP server for a libSDRForge receiver.

The receiver is injected so the protocol can be tested without SDR hardware.
"""
from __future__ import annotations

import socketserver

from sdrforge.interfaces.receiver_control import ReceiverControlIf
from sdrforge.protocols.rigctl.command_handler import RigctlCommandHandler


class RigctlServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, receiver: ReceiverControlIf, host: str = "127.0.0.1",
                 port: int = 4532) -> None:
        self.receiver: ReceiverControlIf = receiver
        super().__init__((host, port), RigctlHandler)


class RigctlHandler(socketserver.StreamRequestHandler):
    server: RigctlServer
    def handle(self) -> None:
        # ORC currently uses one command per TCP connection.
        for raw in self.rfile:
            command = raw.decode("utf-8", errors="replace").strip()
            if not command:
                continue
            try:
                response = RigctlCommandHandler(self.server.receiver).dispatch(command)
            except (ValueError, RuntimeError, OSError):
                response = "RPRT -1"
            self.wfile.write((response + "\n").encode("utf-8"))
            self.wfile.flush()

