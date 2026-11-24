# SPDX-License-Identifier: MIT
"""!
@brief Small localhost RigCTL-compatible TCP server for a libSDRForge receiver.

The receiver is injected so the protocol can be tested without SDR hardware.
"""

from __future__ import annotations

import socketserver

from sdrforge.interfaces.receiver_control_if import ReceiverControlIf
from sdrforge.protocols.rigctl.command_handler import RigctlCommandHandler


class RigctlServer(socketserver.ThreadingTCPServer):
    """!
    @brief Provide rigctl server behavior.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self, receiver: ReceiverControlIf, host: str = "127.0.0.1", port: int = 4532
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param receiver The ``receiver`` value.
        @param host The ``host`` value.
        @param port The ``port`` value.
        """
        self.receiver: ReceiverControlIf = receiver
        super().__init__((host, port), RigctlHandler)


class RigctlHandler(socketserver.StreamRequestHandler):
    """!
    @brief Provide rigctl handler behavior.
    """

    server: RigctlServer

    def handle(self) -> None:
        # ORC currently uses one command per TCP connection.
        """!
        @brief Handle the component.

        @param self The current instance.
        """
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
