# SPDX-License-Identifier: MIT
"""Hardware-independent audio callback regression tests."""

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from sdrforge.adapters.local_audio_sink import LocalAudioSink


class FakeStream:
    """Capture audio callbacks without opening an audio device."""

    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.channels = kwargs["channels"]
        self.started = False
        self.aborted = False
        self.closed = False

    def start(self):
        self.started = True

    def abort(self):
        self.aborted = True

    def close(self):
        self.closed = True

    def render(self, frames):
        output = np.empty((frames, self.channels), dtype=np.float32)
        self.callback(output, frames, None, None)
        return output


@pytest.fixture
def audio(monkeypatch):
    streams = []

    def open_stream(**kwargs):
        stream = FakeStream(**kwargs)
        streams.append(stream)
        return stream

    monkeypatch.setitem(
        sys.modules, "sounddevice", SimpleNamespace(OutputStream=open_stream)
    )
    sink = LocalAudioSink(sample_rate=100)
    yield sink, streams
    sink.close()


def test_prebuffer_and_underrun_recovery(audio):
    sink, streams = audio
    assert sink.diagnostics()["state"] == "STOPPED"
    sink.write(np.full(30, 0.5))
    assert not streams
    assert sink.diagnostics()["state"] == "BUFFERING"
    sink.write(np.full(30, 0.5))
    stream = streams[0]
    assert stream.started
    np.testing.assert_array_equal(stream.render(50), 0.5)
    assert sink.diagnostics()["state"] == "PLAYING"
    np.testing.assert_array_equal(stream.render(20), 0)
    assert sink.diagnostics()["underruns"] == 1
    assert sink.diagnostics()["rebuffer_count"] == 1
    np.testing.assert_array_equal(stream.render(10), 0)
    assert sink.diagnostics()["underruns"] == 1
    sink.write(np.full(50, 0.5))
    np.testing.assert_array_equal(stream.render(20), 0.5)
    assert sink.diagnostics()["state"] == "PLAYING"


def test_mute_discards_pending_audio(audio):
    sink, streams = audio
    sink.write(np.ones(60))
    sink.set_muted(True)
    assert sink.diagnostics()["state"] == "MUTED"
    assert sink.diagnostics()["buffer_ms"] == 0
    sink.write(np.ones(60))
    np.testing.assert_array_equal(streams[0].render(20), 0)
    sink.set_muted(False)
    sink.write(np.full(60, 0.25))
    np.testing.assert_array_equal(streams[0].render(20), 0.25)


def test_overflow_discards_oldest_chunk(audio):
    sink, streams = audio
    sink.write(np.full(60, 0.25))
    sink.write(np.full(60, 0.75))
    assert sink.diagnostics()["dropped_frames"] == 60
    assert sink.diagnostics()["buffer_ms"] == 600
    np.testing.assert_array_equal(streams[0].render(20), 0.75)


def test_close_and_restart(audio):
    sink, streams = audio
    sink.write(np.ones(60))
    sink.close()
    assert streams[0].aborted
    assert streams[0].closed
    assert sink.diagnostics()["state"] == "STOPPED"
    sink.write(np.full((60, 2), 0.5))
    assert len(streams) == 2
    assert streams[1].channels == 2
    np.testing.assert_array_equal(streams[1].render(20), 0.5)
