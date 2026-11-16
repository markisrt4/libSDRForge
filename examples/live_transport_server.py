# SPDX-License-Identifier: MIT
"""Real RTL-SDR REST, rigctl and ZMQ server.

Audio is decoded but not played by this diagnostic service. The radio source
is owned by one worker; REST and rigctl share one ReceiverManager.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import signal
import threading
import time
from contextlib import ExitStack

from sdrforge.adapters.simulated_iq import SimulatedIqSource
from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.protocols.rest.server import RestControlServer
from sdrforge.protocols.rigctl.server import RigctlServer
from sdrforge.session import RadioSession
from sdrforge.telemetry.iq_observer import IqSpectrumObserver
from sdrforge.telemetry.stream import TelemetryStream


class LiveRadioControl:
    """Control one RadioSession without accessing its DSP from server threads."""

    def __init__(
        self, stream: TelemetryStream, *, frequency_hz: int = 104_300_000,
        gain_db: float | None = 29.7, rds_enabled: bool = True,
        warmup_seconds: float = 2.0, simulate: bool = False,
    ) -> None:
        self.frequency_hz = frequency_hz
        self.gain_db = gain_db
        self.rds_enabled = rds_enabled
        self.warmup_seconds = warmup_seconds
        self.stream = stream
        self.simulate = simulate
        self._session: RadioSession | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._error: str | None = None
        self._mode = ("WFM", 200_000)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("radio worker already exists")
        observer = IqSpectrumObserver(self.stream, rate_hz=10.0)
        session = RadioSession(
            frequency_hz=self.frequency_hz,
            mode="stereo", rds_enabled=self.rds_enabled,
            gain_db=self.gain_db, rf_warmup_seconds=self.warmup_seconds,
            iq_observer=observer,
            source=SimulatedIqSource() if self.simulate else None,
        )
        session.start()
        self._session = session
        self._error = None
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="sdrforge-radio", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        session = self._session
        if session is None:
            return
        next_receiver = time.monotonic()
        try:
            while not self._stop.is_set():
                session.read()
                now = time.monotonic()
                if now >= next_receiver:
                    self.stream.submit_receiver(session.receiver)
                    next_receiver = now + 1.0
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self._error = str(exc)
        finally:
            try:
                session.stop()
            except (OSError, RuntimeError) as exc:
                self._error = str(exc)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            raise RuntimeError("radio worker did not stop within five seconds")
        self._thread = None
        self._session = None

    def set_frequency(self, hz: int) -> None:
        if hz <= 0:
            raise ValueError("frequency must be positive")
        running = self._thread is not None
        if running:
            self.stop()
        self.frequency_hz = hz
        if running:
            self.start()

    def get_frequency(self) -> int:
        return self.frequency_hz

    def set_mode(self, mode: str, bandwidth: int) -> None:
        if mode != "WFM":
            raise ValueError("live radio currently supports WFM only")
        self._mode = (mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        return self._mode

    def get_signal_strength(self) -> float | None:
        return None

    def get_snr(self) -> float | None:
        return None

    def get_rds(self) -> str | None:
        session = self._session
        if session is None:
            return None
        status = session.receiver.rds_status
        return None if status is None else str(status)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", type=float, default=104.3, help="FM MHz")
    parser.add_argument("--gain", type=float, default=29.7)
    parser.add_argument("--warmup", type=float, default=2.0)
    parser.add_argument("--no-rds", action="store_true")
    parser.add_argument("--simulate", action="store_true", help="Use synthetic IQ; no USB needed")
    parser.add_argument("--rest-port", type=int, default=5570)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--stop-running", action="store_true",
                        help="Gracefully stop an existing server and exit")
    action.add_argument("--replace-running", action="store_true",
                        help="Gracefully stop an existing server before starting")
    parser.add_argument("--rigctl-port", type=int, default=4532)
    parser.add_argument("--zmq-endpoint", default="tcp://127.0.0.1:5571")
    args = parser.parse_args()
    if not 87.5 <= args.frequency <= 108.0:
        parser.error("frequency must be between 87.5 and 108 MHz")
    base_url = f"http://127.0.0.1:{args.rest_port}"

    def server_alive() -> bool:
        try:
            with urllib.request.urlopen(base_url + "/v1/health", timeout=0.7) as response:
                return response.status == 200 and json.load(response).get("status") == "ok"
        except (OSError, ValueError):
            return False

    running = server_alive()
    if args.stop_running or args.replace_running:
        if running:
            request = urllib.request.Request(
                base_url + "/v1/server/shutdown", data=b"", method="POST"
            )
            try:
                with urllib.request.urlopen(request, timeout=2) as response:
                    if response.status != 200:
                        raise RuntimeError(f"shutdown returned HTTP {response.status}")
            except (OSError, urllib.error.HTTPError) as exc:
                print(f"Cannot gracefully stop existing server: {exc}", flush=True)
                print("The running server may need upgrading; stop it manually first.", flush=True)
                return 1
            for _ in range(40):
                if not server_alive():
                    break
                time.sleep(0.25)
            else:
                print("Existing server did not shut down within ten seconds.", flush=True)
                return 1
            time.sleep(0.25)
            print("Existing SDRForge server stopped.", flush=True)
        elif args.stop_running:
            print("No running SDRForge REST server found.", flush=True)
        if args.stop_running:
            return 0
    elif running:
        print(f"SDRForge is already running at {base_url}.", flush=True)
        print("Use --replace-running to restart or --stop-running to shut it down.", flush=True)
        return 0

    stopping = threading.Event()

    def on_signal(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    with ExitStack() as stack:
        stream = TelemetryStream(endpoint=args.zmq_endpoint)
        stream.start()
        stack.callback(stream.stop)
        control = LiveRadioControl(
            stream, frequency_hz=round(args.frequency * 1_000_000),
            gain_db=args.gain, rds_enabled=not args.no_rds,
            warmup_seconds=args.warmup, simulate=args.simulate,
        )
        manager = ReceiverManager(control)
        stack.callback(manager.stop)
        rest = RestControlServer(manager, "127.0.0.1", args.rest_port,
                                 shutdown_callback=stopping.set)
        stack.callback(rest.server_close)
        rigctl = RigctlServer(manager, "127.0.0.1", args.rigctl_port)
        stack.callback(rigctl.server_close)
        threads = []
        for server in (rest, rigctl):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
        print(f"REST: http://127.0.0.1:{rest.server_port}", flush=True)
        print(f"rigctl: 127.0.0.1:{rigctl.server_address[1]}", flush=True)
        print(f"ZMQ: {args.zmq_endpoint}", flush=True)
        print("Source: simulated IQ" if args.simulate else "Source: RTL-SDR USB", flush=True)
        print("Use REST POST /v1/receiver/start to start acquisition.", flush=True)
        try:
            while not stopping.wait(0.25):
                pass
        finally:
            for server in (rest, rigctl):
                server.shutdown()
            for thread in threads:
                thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
