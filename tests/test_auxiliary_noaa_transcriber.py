"""Auxiliary NOAA worker tests; no SDR, USB or Vosk model required."""
import threading

import numpy as np
import pytest

from sdrforge.weather.auxiliary_transcriber import AuxiliaryNoaaTranscriber
from sdrforge.weather.transcription import NoaaTranscriptionPipeline


class Recognizer:
    def __init__(self):
        self.calls = []

    def transcribe(self, pcm, sample_rate):
        self.calls.append((len(pcm), sample_rate))
        return "temperature is forty two degrees"


def test_auxiliary_worker_emits_observation_without_receiver_calls():
    recognizer = Recognizer()
    emitted = []
    worker = AuxiliaryNoaaTranscriber(
        NoaaTranscriptionPipeline(recognizer, frequency_hz=162_550_000),
        emitted.append,
        segment_seconds=0.1,
    )
    worker.start()
    worker.feed(np.zeros(1600, dtype=np.float32))
    worker.stop()
    assert recognizer.calls == [(1600, 16000)]
    assert len(emitted) == 1
    assert emitted[0]["receiver"] == "auxiliary"
    assert emitted[0]["observation"]["temperature_f"] == 42
    assert emitted[0]["frequency_hz"] == 162_550_000


def test_auxiliary_worker_drops_instead_of_blocking_when_full():
    gate = threading.Event()
    entered = threading.Event()

    class SlowRecognizer:
        def transcribe(self, pcm, sample_rate):
            entered.set()
            assert gate.wait(3)
            return ""

    worker = AuxiliaryNoaaTranscriber(
        NoaaTranscriptionPipeline(SlowRecognizer()), lambda _: None,
        segment_seconds=0.01, queue_capacity=1,
    )
    worker.start()
    try:
        worker.feed(np.zeros(160, dtype=np.float32))
        assert entered.wait(2)
        worker.feed(np.zeros(160 * 4, dtype=np.float32))
        assert worker.dropped_segments == 3
    finally:
        gate.set()
        worker.stop(timeout=3)


@pytest.mark.parametrize("audio", [
    np.array([float("nan")]),
    np.array([1.5]),
    np.zeros((2, 2)),
])
def test_auxiliary_worker_rejects_invalid_pcm(audio):
    worker = AuxiliaryNoaaTranscriber(
        NoaaTranscriptionPipeline(Recognizer()), lambda _: None,
    )
    worker.start()
    try:
        with pytest.raises(ValueError):
            worker.feed(audio)
    finally:
        worker.stop()
