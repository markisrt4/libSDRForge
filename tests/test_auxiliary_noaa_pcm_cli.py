"""Hardware-free tests for the auxiliary PCM streaming CLI."""

import io
import json
import sys

import numpy as np

from sdrforge.weather import auxiliary_pcm


class FakeNativeVosk:
    def __init__(self, model, library):
        self.model = model
        self.library = library

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def transcribe(self, pcm, sample_rate):
        assert sample_rate == 16000
        return "temperature is forty two degrees"


class FakeStdin:
    def __init__(self, audio):
        self.buffer = io.BytesIO(audio)


def test_auxiliary_pcm_stream_emits_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(auxiliary_pcm, "VoskNativeAdapter", FakeNativeVosk)
    monkeypatch.setattr(
        sys,
        "stdin",
        FakeStdin(np.zeros(1600, dtype="<i2").tobytes()),
    )
    destination = tmp_path / "observations.jsonl"
    assert (
        auxiliary_pcm.main(
            [
                "--model",
                str(tmp_path),
                "--vosk-library",
                str(tmp_path / "libvosk.so"),
                "--segment-seconds",
                "0.1",
                "--jsonl",
                str(destination),
            ]
        )
        == 0
    )
    lines = destination.read_text().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["receiver"] == "auxiliary"
    assert event["frequency_hz"] == 162550000
    assert event["observation"]["temperature_f"] == 42


def test_auxiliary_pcm_empty_stream(monkeypatch, tmp_path):
    monkeypatch.setattr(auxiliary_pcm, "VoskNativeAdapter", FakeNativeVosk)
    monkeypatch.setattr(sys, "stdin", FakeStdin(b""))
    destination = tmp_path / "empty.jsonl"
    assert (
        auxiliary_pcm.main(
            [
                "--model",
                str(tmp_path),
                "--vosk-library",
                str(tmp_path / "libvosk.so"),
                "--jsonl",
                str(destination),
            ]
        )
        == 0
    )
    assert destination.read_text() == ""
