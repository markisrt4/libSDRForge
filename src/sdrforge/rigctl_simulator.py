"""Run a simulated libSDRForge RigCTL receiver for ORC CLI integration tests.

Run: python -m sdrforge.rigctl_simulator --port 4532
No SDR dongle or audio hardware required.
"""
from __future__ import annotations

import argparse

from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.rigctl_server import RigctlServer
from sdrforge.simulation.simulated_receiver import SimulatedReceiver



def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated libSDRForge RigCTL receiver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4532)
    parser.add_argument("--frequency", type=int, default=104_300_000)
    args = parser.parse_args()
    if args.frequency <= 0:
        parser.error("frequency must be positive")
    with RigctlServer(ReceiverManager(SimulatedReceiver(args.frequency)), args.host, args.port) as server:
        print(f"RigCTL simulator listening on {server.server_address}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
