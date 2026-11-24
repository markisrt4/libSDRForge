"""Hardware-free regression tests for stale PCM after a mode change."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
from test_live_transport_server import load_live_server

from sdrforge.adapters.local_audio_sink import LocalAudioSink


def test_stale_audio_generation_is_discarded() -> None:
    """The radio worker must flush old PCM before submitting new-mode audio."""
    module = load_live_server()
    control = module.LiveRadioControl(stream=Mock())
    control.audio = LocalAudioSink(sample_rate=100)
    control.audio.submit_pcm(np.ones((60, 1), dtype=np.float32))
    current = np.full((60, 1), 0.25, dtype=np.float32)
    session = Mock()
    session._demodulation = "AM"
    session.channel_bandwidth_hz = 10_000
    session.frequency_hz = 104_300_000

    def read():
        control._stop.set()
        return SimpleNamespace(audio=current)

    session.read.side_effect = read
    control._session = session
    control._pending_mode = ("AM", 10_000)
    control._run()

    session.set_demodulation.assert_called_once_with("AM", 10_000)
    output = np.zeros_like(current)
    control.audio._render_audio(output, len(output), None, None)
    np.testing.assert_array_equal(output, current)
