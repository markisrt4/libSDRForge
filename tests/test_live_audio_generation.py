"""Hardware-free regression tests for live audio generation fencing."""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from live_transport_server import LiveRadioControl


class FakeAudio:
    """Capture playback and stop the worker after one valid frame."""

    def __init__(self, stop: threading.Event) -> None:
        self.written: list[object] = []
        self._stop = stop

    def write(self, pcm: object) -> None:
        self.written.append(pcm)
        self._stop.set()


def test_stale_audio_generation_is_discarded() -> None:
    """An already-dequeued old-mode frame must not reach the audio sink."""
    control = object.__new__(LiveRadioControl)
    control._audio_queue = queue.Queue()
    control._audio_stop = threading.Event()
    control._audio_lock = threading.Lock()
    control._audio_generation = 2
    control._audio_error = None
    control.audio = FakeAudio(control._audio_stop)
    stale = object()
    current = object()
    control._audio_queue.put_nowait((1, stale))
    control._audio_queue.put_nowait((2, current))

    control._play_audio()

    assert control.audio.written == [current]
