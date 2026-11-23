# SPDX-License-Identifier: MIT
"""Hardware-free REST, rigctl and ZeroMQ integration demo.

Run: python component_test/transport_demo_server.py
Stop: Ctrl+C. All interfaces bind to loopback by default.
"""
from __future__ import annotations

import argparse
import signal
import threading
from contextlib import ExitStack

import numpy as np

from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.protocols.rest.server import RestControlServer
from sdrforge.protocols.rigctl.server import RigctlServer
from sdrforge.simulation.simulated_receiver import SimulatedReceiver
from sdrforge.telemetry.stream import TelemetryStream


class DemoTelemetry:
    """Expose the receiver snapshot fields without actual DSP hardware."""

    def __init__(self, control: ReceiverManager) -> None:
        self.control = control

    @property
    def channel_frequency_hz(self) -> int:
        return self.control.get_frequency()

    @property
    def stereo_locked(self) -> bool:
        return self.control.running

    @property
    def stereo_blend(self) -> float:
        return 1.0 if self.control.running else 0.0

    @property
    def rds_status(self) -> None:
        return None

    @property
    def last_rds_groups(self) -> tuple:
        return ()

    @property
    def tmc_candidate_report(self) -> dict:
        return {"candidate_count": 0, "usable_for_navigation": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--rest-port", type=int, default=5570)
    parser.add_argument("--rigctl-port", type=int, default=4532)
    parser.add_argument("--zmq-endpoint", default="tcp://127.0.0.1:5571")
    args = parser.parse_args()

    receiver = ReceiverManager(SimulatedReceiver())
    telemetry = DemoTelemetry(receiver)
    stop = threading.Event()

    def shutdown(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    with ExitStack() as stack:
        rest = RestControlServer(receiver, args.host, args.rest_port)
        stack.callback(rest.server_close)
        rigctl = RigctlServer(receiver, args.host, args.rigctl_port)
        stack.callback(rigctl.server_close)
        stream = TelemetryStream(endpoint=args.zmq_endpoint)
        stream.start()
        stack.callback(stream.stop)

        threads = []
        for server in (rest, rigctl):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
            stack.callback(server.shutdown)
        print(f"REST: http://{args.host}:{rest.server_port}", flush=True)
        print(f"rigctl: {args.host}:{rigctl.server_address[1]}", flush=True)
        print(f"ZMQ: {args.zmq_endpoint}", flush=True)
        print("Synthetic telemetry running. Ctrl+C to stop.", flush=True)

        phase = 0.0
        while not stop.wait(0.1):
            phase += 0.13
            bins = np.arange(256, dtype=np.float32)
            spectrum = -85.0 + 36.0 * np.exp(-((bins - 128) / 8) ** 2)
            spectrum += 2.0 * np.sin(bins / 13 + phase)
            stream.submit_spectrum(
                spectrum,
                center_frequency_hz=receiver.get_frequency(),
                sample_rate_hz=200_000,
            )
            if int(phase * 10) % 10 == 0:
                mode, bandwidth = receiver.get_mode()
                stream.submit_receiver(
                    telemetry,
                    mode="WFM" if mode == "FM" else mode,
                    bandwidth_hz=bandwidth,
                    running=receiver.running,
                )
        for server in (rest, rigctl):
            server.shutdown()
        for thread in threads:
            thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
