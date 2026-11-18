"""Auxiliary-only NOAA RF IQ -> NFM -> 16 kHz mono PCM bridge.

Accepts IQ blocks supplied by an explicitly owned auxiliary SDR source.
Never opens hardware, tunes a receiver, or accesses primary audio.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from sdrforge.receivers.nbfm_mono_demodulator import NbfmMonoDemodulator


class AuxiliaryNoaaIqBridge:
    """Stream 2.4 MSPS U8 IQ into a lease-guarded NOAA PCM session.

    NbfmMonoDemodulator outputs 48 kHz audio. An anti-aliasing FIR decimator
    produces 16 kHz audio without resetting its history at block boundaries.
    The session enforces WEATHER ownership before accepting the audio.
    """

    def __init__(self, session, *, demodulator=None) -> None:
        self.session = session
        self.demodulator = demodulator or NbfmMonoDemodulator()
        self._fir = signal.firwin(97, 7_200, fs=48_000)
        self._state = np.zeros(len(self._fir) - 1, dtype=np.float64)
        self._phase = 0
        self.iq_blocks = 0
        self.pcm_samples = 0

    def process(self, iq_block) -> int:
        """Demodulate one auxiliary IQ block and forward 16 kHz PCM."""
        # Check ownership before doing expensive DSP or consuming any IQ.
        self.session.require_weather()
        pcm48 = self.demodulator.process(iq_block)
        if not len(pcm48):
            return 0
        filtered, self._state = signal.lfilter(
            self._fir, [1.0], pcm48, zi=self._state
        )
        pcm16 = filtered[self._phase::3].astype(np.float32)
        self._phase = (self._phase - len(filtered)) % 3
        if len(pcm16):
            # NFM discriminator output is not guaranteed to be normalized.\n            # Limit at the audio boundary, preserving strict PCM validation\n            # in the transcription pipeline.\n            pcm16 = np.nan_to_num(pcm16, nan=0.0, posinf=1.0, neginf=-1.0)\n            np.clip(pcm16, -1.0, 1.0, out=pcm16)\n            self.session.feed(pcm16)
        self.iq_blocks += 1
        self.pcm_samples += len(pcm16)
        return len(pcm16)
