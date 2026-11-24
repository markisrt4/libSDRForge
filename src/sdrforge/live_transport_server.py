# SPDX-License-Identifier: MIT
"""Real RTL-SDR REST, rigctl and ZMQ server.

Audio is decoded and played through the optional local PCM audio sink. The radio source
is owned by one worker; REST and rigctl share one ReceiverManager.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

from sdrforge.adapters.json_preset_store import JsonPresetStore
from sdrforge.adapters.local_audio_sink import LocalAudioSink
from sdrforge.adapters.preset_paths import default_preset_path
from sdrforge.adapters.regional_radio_catalog import load_radio_catalog
from sdrforge.adapters.simulated_iq import SimulatedIqSource
from sdrforge.controllers.radio_catalog import PresetService
from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.protocols.rest.radio_api import RadioApi
from sdrforge.protocols.rest.server import RestControlServer
from sdrforge.protocols.rigctl.server import RigctlServer
from sdrforge.session import RadioSession
from sdrforge.telemetry.iq_observer import IqSpectrumObserver
from sdrforge.telemetry.stream import TelemetryStream


class IqCapture:
    """Bounded, nonblocking IQ recording from the existing acquisition stream."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._lock = threading.Lock()
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=64)
        self._active = False
        self._status: dict[str, object] = {"state": "idle"}
        self._remaining = 0
        self._deadline = 0.0
        self._thread: threading.Thread | None = None

    def start(
        self,
        duration_seconds: int,
        filename: str,
        *,
        frequency_hz: int,
        sample_rate_hz: int,
        gain_db: float | None,
    ) -> dict:
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 120:
            raise ValueError("duration_seconds must be an integer from 1 to 120")
        if (
            not filename.endswith(".iq")
            or Path(filename).name != filename
            or filename in (".iq", "..iq")
        ):
            raise ValueError("filename must be a simple .iq filename")
        with self._lock:
            if self._active or (self._thread is not None and self._thread.is_alive()):
                raise RuntimeError("IQ capture already active")
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / filename
            if path.exists() or path.with_suffix(".json").exists():
                raise ValueError("capture file already exists")
            self._queue = queue.Queue(maxsize=64)
            self._remaining = duration_seconds * sample_rate_hz
            self._deadline = (
                time.monotonic() + duration_seconds + max(10, duration_seconds // 2)
            )
            self._status = {
                "state": "capturing",
                "filename": str(path),
                "metadata_filename": str(path.with_suffix(".json")),
                "duration_seconds": duration_seconds,
                "frequency_hz": frequency_hz,
                "sample_rate_hz": sample_rate_hz,
                "gain_db": gain_db,
                "format": "u8_interleaved_iq",
                "samples_written": 0,
                "dropped_blocks": 0,
                "started_at_ns": time.time_ns(),
                "complete": False,
            }
            self._active = True
            self._thread = threading.Thread(
                target=self._write,
                args=(path,),
                daemon=True,
                name="sdrforge-iq-capture",
            )
            self._thread.start()
            return dict(self._status)

    def observe(self, block) -> None:
        with self._lock:
            if not self._active:
                return
            if (
                block.center_frequency_hz != self._status["frequency_hz"]
                or block.sample_rate_hz != self._status["sample_rate_hz"]
            ):
                self._finish_locked("frequency_changed")
                return
            count = min(len(block.samples) // 2, self._remaining)
            if count:
                try:
                    self._queue.put_nowait(block.samples[: count * 2])
                except queue.Full:
                    self._status["dropped_blocks"] += 1
                self._remaining -= count
            if self._remaining <= 0:
                self._finish_locked("complete")

    def _finish_locked(self, reason: str) -> None:
        if self._active:
            self._active = False
            self._status["state"] = "finalizing"
            self._status["stop_reason"] = reason

    def stop(self) -> None:
        with self._lock:
            self._finish_locked("receiver_stopped")

    def cancel(self) -> dict:
        with self._lock:
            self._finish_locked("cancelled")
            return dict(self._status)

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _write(self, path: Path) -> None:
        try:
            with path.open("xb") as output:
                while True:
                    try:
                        samples = self._queue.get(timeout=0.1)
                    except queue.Empty:
                        with self._lock:
                            if self._active and time.monotonic() >= self._deadline:
                                self._finish_locked("timeout")
                            if not self._active and self._queue.empty():
                                break
                        continue
                    output.write(samples)
                    with self._lock:
                        self._status["samples_written"] += len(samples) // 2
            with self._lock:
                self._status["complete"] = (
                    self._status.get("stop_reason") == "complete"
                    and self._status["dropped_blocks"] == 0
                )
                self._status["state"] = (
                    "complete" if self._status["complete"] else "incomplete"
                )
                self._status["finished_at_ns"] = time.time_ns()
                metadata = dict(self._status)
            path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
        except OSError as exc:
            with self._lock:
                self._active = False
                self._status["state"] = "error"
                self._status["error"] = str(exc)


class LiveRadioControl:
    """Control one RadioSession without accessing its DSP from server threads."""

    def __init__(
        self,
        stream: TelemetryStream,
        *,
        frequency_hz: int = 104_300_000,
        gain_db: float | None = 29.7,
        rds_enabled: bool = True,
        warmup_seconds: float = 2.0,
        simulate: bool = False,
    ) -> None:
        self.frequency_hz = frequency_hz
        self.gain_db = gain_db
        self.sample_rate_hz = 2_400_000
        self.rtl_agc_enabled = False
        self.ppm_correction = 0
        self.rds_enabled = rds_enabled
        self.warmup_seconds = warmup_seconds
        self.stream = stream
        self.simulate = simulate
        self.audio = LocalAudioSink()
        self._audio_error: str | None = None
        self._audio_stop = threading.Event()
        self._audio_thread: threading.Thread | None = None
        self._session: RadioSession | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._error: str | None = None
        self._mode = ("WFM", 200_000)
        self._tune_lock = threading.Lock()
        self._pending_frequency: int | None = None
        self._pending_recenter = False
        self._pending_pan: int | None = None
        self._pending_mode: tuple[str, int] | None = None
        self._capture_manager = None
        self._auto_capture_thread = None
        self.capture = IqCapture(
            Path(
                os.environ.get(
                    "SDRFORGE_CAPTURE_DIR",
                    str(Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "sdrforge/captures"),
                )
            )
        )

    def _make_source(self):
        from sdrforge.adapters.rtl_sdr import RtlSdrSource

        source = RtlSdrSource()
        source._rtl_agc_enabled = self.rtl_agc_enabled
        source._ppm_correction = self.ppm_correction
        return source

    @property
    def worker_alive(self) -> bool:
        """Report acquisition worker liveness independently of REST lifecycle."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def worker_error(self) -> str | None:
        """Expose the most recent acquisition failure to REST status."""
        return self._error

    def start(self) -> None:
        if self._thread is not None:
            if self._thread.is_alive():
                raise RuntimeError("radio worker already exists")
            # A failed USB read can end the worker without an explicit stop.
            # Retire its completed thread before attempting a fresh source open.
            self.stop()
        if self._audio_thread is not None and self._audio_thread.is_alive():
            raise RuntimeError("Previous audio worker has not stopped")
        spectrum = IqSpectrumObserver(self.stream, rate_hz=10.0)

        def observer(block):
            self.capture.observe(block)
            spectrum(block)

        session = RadioSession(
            frequency_hz=self.frequency_hz,
            mode="stereo",
            rds_enabled=self.rds_enabled,
            gain_db=self.gain_db,
            rf_warmup_seconds=self.warmup_seconds,
            iq_observer=observer,
            source=SimulatedIqSource() if self.simulate else self._make_source(),
        )
        session.set_demodulation(*self._mode)
        session.start()
        self._session = session
        self.audio.reset_buffer()
        self._audio_stop = threading.Event()
        self._audio_thread = threading.Thread(
            target=self._service_audio, name="sdrforge-audio", daemon=True
        )
        self._audio_thread.start()
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
                with self._tune_lock:
                    pending = self._pending_frequency
                    self._pending_frequency = None
                    recenter = self._pending_recenter
                    self._pending_recenter = False
                    pan = self._pending_pan
                    self._pending_pan = None
                    pending_mode = self._pending_mode
                    self._pending_mode = None
                if pending_mode is not None:
                    session.set_demodulation(*pending_mode)
                if pending is not None:
                    session.retune(pending)
                centered = session.recenter() if recenter else False
                if pan is not None:
                    centered = session.pan_acquisition(pan) or centered
                    with self._tune_lock:
                        if self._pending_frequency is None:
                            self.frequency_hz = session.frequency_hz
                if pending_mode is not None or pending is not None or centered:
                    self.audio.reset_buffer()
                try:
                    frame = session.read()
                except ValueError as exc:
                    # Asynchronous IQ may contain buffered blocks from the old
                    # center frequency immediately after a hardware retune.
                    if "unexpected source center frequency" in str(exc):
                        continue
                    raise
                self.audio.submit_pcm(frame.audio)
                now = time.monotonic()
                if now >= next_receiver:
                    self.stream.submit_receiver(
                        session.receiver,
                        mode=session._demodulation,
                        bandwidth_hz=session.channel_bandwidth_hz,
                        frequency_hz=session.frequency_hz,
                        running=True,
                    )
                    next_receiver = now + 1.0
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self._error = str(exc)
        finally:
            self._audio_stop.set()
            try:
                self.capture.stop()
            finally:
                try:
                    session.stop()
                except (OSError, RuntimeError) as exc:
                    self._error = str(exc)
                finally:
                    if self._audio_thread is not None:
                        self._audio_thread.join(timeout=2.0)
                        if self._audio_thread.is_alive():
                            print(
                                "SDRForge audio device blocked; restart waits for cleanup",
                                flush=True,
                            )
                        else:
                            self._audio_thread = None

    def _service_audio(self) -> None:
        try:
            while not self._audio_stop.is_set():
                try:
                    self.audio.service_device()
                except (OSError, RuntimeError, ValueError) as exc:
                    if self._audio_error != str(exc):
                        self._audio_error = str(exc)
                        print(f"SDRForge audio output unavailable: {exc}", flush=True)
                    self.audio.set_muted(True)
                self._audio_stop.wait(0.01)
        finally:
            try:
                self.audio.close()
            except (OSError, RuntimeError) as exc:
                self._audio_error = str(exc)

    def stop(self) -> None:
        if self._thread is None:
            return
        self.capture.stop()
        self._stop.set()
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            raise RuntimeError("radio worker did not stop within five seconds")
        self._thread = None
        self._session = None

    def start_iq_capture(self, duration_seconds: int, filename: str) -> dict:
        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError(
                "receiver is stopped; start it and wait for running=true before capturing IQ"
            )
        session = self._session
        if session is None:
            raise RuntimeError("receiver session unavailable")
        return self.capture.start(
            duration_seconds,
            filename,
            frequency_hz=session.acquisition_frequency_hz,
            sample_rate_hz=self.sample_rate_hz,
            gain_db=self.gain_db,
        )

    def start_automated_iq_capture(self, duration_seconds: int, filename: str) -> dict:
        """Start acquisition when necessary, then capture without blocking REST."""
        if self._capture_manager is None:
            raise RuntimeError("receiver manager unavailable")
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 120:
            raise ValueError("duration_seconds must be an integer from 1 to 120")
        if (
            not filename.endswith(".iq")
            or Path(filename).name != filename
            or filename in (".iq", "..iq")
        ):
            raise ValueError("filename must be a simple .iq filename")
        with self.capture._lock:
            if self.capture._active or (
                self.capture._thread is not None and self.capture._thread.is_alive()
            ):
                raise RuntimeError("IQ capture already active")
            if (
                self.capture.directory.joinpath(filename).exists()
                or self.capture.directory.joinpath(filename)
                .with_suffix(".json")
                .exists()
            ):
                raise ValueError("capture file already exists")
        if (
            self._auto_capture_thread is not None
            and self._auto_capture_thread.is_alive()
        ):
            raise RuntimeError("automated IQ capture already active")
        manager = self._capture_manager
        owned = not manager.running and not manager.starting
        if owned:
            manager.start_async()

        def worker() -> None:
            try:
                deadline = time.monotonic() + 30
                while not manager.running:
                    if manager.startup_error:
                        raise RuntimeError(str(manager.startup_error))
                    if time.monotonic() >= deadline:
                        raise TimeoutError("receiver startup exceeded 30 seconds")
                    time.sleep(0.1)
                self.start_iq_capture(duration_seconds, filename)
                while True:
                    status = self.capture.status()
                    if status["state"] in ("complete", "incomplete", "error"):
                        break
                    time.sleep(0.1)
            except Exception as exc:  # noqa: BLE001 - report unexpected worker failures
                print(f"Automated IQ capture failed: {exc}", flush=True)
                with self.capture._lock:
                    if not self.capture._active:
                        self.capture._status = {
                            "state": "error",
                            "error": str(exc),
                            "filename": filename,
                        }
            finally:
                if owned:
                    try:
                        manager.stop()
                    except Exception as exc:  # noqa: BLE001 - cleanup must not mask capture error
                        print(
                            f"Automated capture receiver cleanup failed: {exc}",
                            flush=True,
                        )

        self._auto_capture_thread = threading.Thread(
            target=worker, name="sdrforge-auto-capture", daemon=True
        )
        self._auto_capture_thread.start()
        return {
            "state": "starting_receiver" if owned else "waiting_for_receiver",
            "filename": filename,
            "auto_start_receiver": True,
            "stop_receiver_after_capture": owned,
        }

    def iq_capture_status(self) -> dict:
        return self.capture.status()

    def cancel_iq_capture(self) -> dict:
        return self.capture.cancel()

    def pan_acquisition(self, center_hz: int) -> None:
        if center_hz <= 0:
            raise ValueError("acquisition center must be positive")
        with self._tune_lock:
            if self._thread is None or not self._thread.is_alive():
                raise RuntimeError("receiver is not running")
            self._pending_pan = center_hz

    def recenter(self) -> None:
        """Queue a one-shot acquisition recenter on the radio worker."""
        with self._tune_lock:
            if self._thread is None or not self._thread.is_alive():
                raise RuntimeError("receiver is not running")
            self._pending_recenter = True

    def set_frequency(self, hz: int) -> None:
        if hz <= 0:
            raise ValueError("frequency must be positive")
        with self._tune_lock:
            self.frequency_hz = hz
            if self._thread is not None:
                self._pending_frequency = hz

    def get_rf_configuration(self) -> dict[str, object]:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "gain_db": self.gain_db,
            "rtl_agc_enabled": self.rtl_agc_enabled,
            "ppm_correction": self.ppm_correction,
            # Settings are only editable while stopped; the next start applies them.
            "restart_required": False,
        }

    def set_rf_configuration(self, changes: dict[str, object]) -> None:
        """Validate settings; defer hardware changes until the next acquisition."""
        if self._thread is not None:
            raise RuntimeError("stop receiver before changing RF hardware settings")
        allowed = {"sample_rate_hz", "gain_db", "rtl_agc_enabled", "ppm_correction"}
        if set(changes) - allowed:
            raise ValueError("unsupported RF settings")
        rate = changes.get("sample_rate_hz", self.sample_rate_hz)
        gain = changes.get("gain_db", self.gain_db)
        agc = changes.get("rtl_agc_enabled", self.rtl_agc_enabled)
        ppm = changes.get("ppm_correction", self.ppm_correction)
        if type(rate) is not int or rate != 2_400_000:
            raise ValueError("WBFM DSP currently requires 2400000 samples/sec")
        if gain is not None and (type(gain) not in (int, float) or not 0 <= gain <= 50):
            raise ValueError("gain_db must be null or between 0 and 50")
        if type(agc) is not bool:
            raise ValueError("rtl_agc_enabled must be boolean")
        if type(ppm) is not int or not -200 <= ppm <= 200:
            raise ValueError("ppm_correction must be an integer between -200 and 200")
        self.sample_rate_hz = rate
        self.gain_db = gain
        self.rtl_agc_enabled = agc
        self.ppm_correction = ppm

    def set_muted(self, muted: bool) -> None:
        self.audio.set_muted(muted)

    def get_audio_diagnostics(self) -> dict:
        """Return local playback diagnostics."""
        return self.audio.diagnostics()

    def get_muted(self) -> bool:
        return self.audio.muted

    def get_frequency(self) -> int:
        return self.frequency_hz

    def set_mode(self, mode: str, bandwidth: int) -> None:
        canonical = "WFM" if mode.upper() == "FM" else mode.upper()
        defaults = {"WFM": 200_000, "NFM": 25_000, "AM": 25_000}
        if canonical not in defaults:
            raise ValueError(f"unsupported radio mode: {mode}")
        selected = bandwidth or defaults[canonical]
        supported = {
            "WFM": (180_000, 200_000),
            "NFM": (7_500, 12_500, 25_000),
            "AM": (6_000, 10_000, 12_500, 25_000),
        }
        if selected not in supported[canonical]:
            raise ValueError(f"unsupported {canonical} bandwidth: {selected}")
        with self._tune_lock:
            self._mode = (canonical, selected)
            if self._thread is not None:
                self._pending_mode = self._mode

    def get_mode(self) -> tuple[str, int]:
        return self._mode

    def get_signal_strength(self) -> float | None:
        return None

    def get_snr(self) -> float | None:
        return None

    def get_rds_status(self) -> dict[str, object] | None:
        """Structured RDS status for REST; rigctl retains its text contract."""
        session = self._session
        if session is None:
            return None
        # RDS belongs to broadcast WFM; NFM and AM demodulators do not
        # expose it. Mode changes must never break REST status polling.
        status = getattr(session.receiver, "rds_status", None)
        if status is None:
            return None
        return asdict(status)

    def get_rds(self) -> str | None:
        status = self.get_rds_status()
        if status is None:
            return None
        metadata = status["metadata"]
        return metadata.get("radio_text") or metadata.get("program_service")


def load_region_environment() -> None:
    """Load data-only regional settings without overriding the environment."""
    config = Path(os.environ.get("SDRFORGE_REGION_CONFIG") or (
        Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        / "sdrforge/radio-region.conf"
    ))
    if not config.is_file():
        return
    for line in config.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in ("SDRFORGE_RADIO_ROOT", "SDRFORGE_RADIO_LOCALE"):
            if value and not os.environ.get(key):
                os.environ[key] = value


def main() -> int:
    load_region_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frequency", type=float, default=104.3, help="Tuning frequency in MHz"
    )
    parser.add_argument(
        "--mode",
        choices=("WFM", "NFM", "AM"),
        default="WFM",
        help="Initial demodulation mode",
    )
    parser.add_argument("--gain", type=float, default=29.7)
    parser.add_argument("--warmup", type=float, default=2.0)
    parser.add_argument("--no-rds", action="store_true")
    parser.add_argument(
        "--simulate", action="store_true", help="Use synthetic IQ; no USB needed"
    )
    parser.add_argument("--rest-port", type=int, default=5570)
    parser.add_argument(
        "--radio-root",
        type=Path,
        default=Path(os.environ["SDRFORGE_RADIO_ROOT"])
        if os.environ.get("SDRFORGE_RADIO_ROOT")
        else None,
        help="Optional external common/locale radio profile directory",
    )
    parser.add_argument(
        "--radio-locale",
        default=os.environ.get("SDRFORGE_RADIO_LOCALE"),
        help="Optional regional directory name under --radio-root",
    )
    parser.add_argument(
        "--presets-path",
        type=Path,
        default=None,
        help="Writable user preset JSON file (default: XDG config)",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--stop-running",
        action="store_true",
        help="Gracefully stop an existing server and exit",
    )
    action.add_argument(
        "--replace-running",
        action="store_true",
        help="Gracefully stop an existing server before starting",
    )
    parser.add_argument("--rigctl-port", type=int, default=4532)
    parser.add_argument("--zmq-endpoint", default="tcp://127.0.0.1:5571")
    args = parser.parse_args()
    if not 24.0 <= args.frequency <= 1766.0:
        parser.error("frequency must be between 24 and 1766 MHz for the R820T tuner")
    base_url = f"http://127.0.0.1:{args.rest_port}"

    def server_alive() -> bool:
        try:
            with urllib.request.urlopen(
                base_url + "/v1/health", timeout=0.7
            ) as response:
                return (
                    response.status == 200 and json.load(response).get("status") == "ok"
                )
        except (OSError, ValueError):
            return False

    def ports_available() -> bool:
        ports = (args.rest_port, args.rigctl_port)
        if args.zmq_endpoint.startswith("tcp://"):
            ports += (int(args.zmq_endpoint.rsplit(":", 1)[1]),)
        for port in ports:
            try:
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True

    running = server_alive()
    # A supervised process is restarted automatically after an HTTP shutdown.
    # Never compete with runit for ownership of its lifecycle.
    service_dir = os.path.join(
        os.environ.get("PREFIX", "/data/data/com.termux/files/usr"),
        "var/service/openroadcode-sdrforge",
    )
    supervised_up = False
    if os.path.isdir(service_dir):
        try:
            status = subprocess.run(
                ["sv", "status", service_dir],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            supervised_up = status.returncode == 0 and status.stdout.startswith("run:")
        except (OSError, subprocess.TimeoutExpired):
            pass
    if running and supervised_up and (args.stop_running or args.replace_running):
        print(
            "SDRForge is managed by runit; refusing direct shutdown/replacement.",
            flush=True,
        )
        print(f"Stop: sv down {service_dir}", flush=True)
        print(f"Start: sv up {service_dir}", flush=True)
        print(f"Restart: sv restart {service_dir}", flush=True)
        return 1
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
                print(
                    "The running server may need upgrading; stop it manually first.",
                    flush=True,
                )
                return 1
            for _ in range(40):
                if not server_alive():
                    break
                time.sleep(0.25)
            else:
                print(
                    "Existing server did not shut down within ten seconds.", flush=True
                )
                return 1
            for _ in range(80):
                if ports_available():
                    break
                time.sleep(0.25)
            else:
                print(
                    "Shutdown acknowledged, but REST/rigctl/ZMQ ports are still occupied.",
                    flush=True,
                )
                print("Inspect listeners with: sudo ss -ltnp", flush=True)
                return 1
            print("Existing SDRForge server stopped and ports released.", flush=True)
        elif args.stop_running:
            print("No running SDRForge REST server found.", flush=True)
        if args.stop_running:
            return 0
    elif running:
        print(f"SDRForge is already running at {base_url}.", flush=True)
        print(
            "Use the service manager if supervised; otherwise use --replace-running or --stop-running.",
            flush=True,
        )
        return 0

    stopping = threading.Event()

    def on_signal(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    with ExitStack() as stack:
        stream = TelemetryStream(endpoint=args.zmq_endpoint)
        try:
            stream.start()
        except RuntimeError as exc:
            print(
                f"Cannot start ZMQ telemetry at {args.zmq_endpoint}: {exc}", flush=True
            )
            print("Inspect listeners with: sudo ss -ltnp", flush=True)
            return 1
        stack.callback(stream.stop)
        control = LiveRadioControl(
            stream,
            frequency_hz=round(args.frequency * 1_000_000),
            gain_db=args.gain,
            rds_enabled=not args.no_rds,
            warmup_seconds=args.warmup,
            simulate=args.simulate,
        )
        control.set_mode(args.mode, 0)
        manager = ReceiverManager(control)
        control._capture_manager = manager
        stack.callback(manager.stop)
        catalog, factory_presets = load_radio_catalog(
            radio_root=args.radio_root,
            locale=args.radio_locale,
        )
        presets_path = args.presets_path or default_preset_path()
        preset_service = PresetService(catalog, JsonPresetStore(presets_path))
        radio_api = RadioApi(catalog, preset_service, factory_presets=factory_presets)
        rest = RestControlServer(
            manager,
            "127.0.0.1",
            args.rest_port,
            shutdown_callback=stopping.set,
            capture_control=control,
            source_type="simulated" if args.simulate else "rtl_sdr",
            radio_api=radio_api,
        )
        stack.callback(rest.server_close)
        rigctl = RigctlServer(manager, "127.0.0.1", args.rigctl_port)
        stack.callback(rigctl.server_close)
        threads = []
        for server in (rest, rigctl):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
        print(f"REST: http://127.0.0.1:{rest.server_port}", flush=True)
        print(f"Radio preset store: {presets_path}", flush=True)
        print(f"rigctl: 127.0.0.1:{rigctl.server_address[1]}", flush=True)
        print(f"ZMQ: {args.zmq_endpoint}", flush=True)
        print(
            "Source: simulated IQ" if args.simulate else "Source: RTL-SDR USB",
            flush=True,
        )
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
