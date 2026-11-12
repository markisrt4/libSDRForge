# SPDX-License-Identifier: MIT
"""RigCTL TCP protocol tests, using a fake receiver and no SDR hardware."""
import socket
import threading

from sdrforge.rigctl_server import RigctlServer


class FakeReceiver:
    def __init__(self):
        self.frequency = 104_300_000
        self.mode = "WFM"
        self.started = False

    def start(self): self.started = True
    def stop(self): self.started = False
    def set_frequency(self, hz): self.frequency = hz
    def get_frequency(self): return self.frequency
    def set_mode(self, mode, bandwidth): self.mode, self.bandwidth = mode, bandwidth
    def get_mode(self): return self.mode, getattr(self, "bandwidth", 200000)
    def get_signal_strength(self): return -32.5
    def get_snr(self): return 19.0
    def get_rds(self): return "TEST STATION"


def test_rigctl_orc_commands():
    receiver = FakeReceiver()
    server = RigctlServer(receiver, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def send(command):
            with socket.create_connection(server.server_address, timeout=2) as connection:
                connection.sendall((command + "\n").encode())
                return connection.recv(4096).decode().strip()

        assert send("f") == "104300000"
        assert send("F 101700000") == "RPRT 0"
        assert send("f") == "101700000"
        assert send("M FM 12000") == "RPRT 0"
        assert receiver.mode == "FM"
        assert send("m") == "FM\\n12000"
        assert send(r"\start") == "RPRT 0"
        assert receiver.started
        assert send("l STRENGTH") == "-32.5"
        assert send("l SNR") == "19.0"
        assert send("l RDS") == "TEST STATION"
        assert send("F 0") == "RPRT -1"
        assert send("garbage") == "RPRT -4"
        assert send(r"\stop") == "RPRT 0"
        assert not receiver.started
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
