"""Experimental NOAA SAME AFSK demodulator for captured mono audio.

SAME is 520 5/6 baud asynchronous 8N1, LSB-first, with nominal
1562.5 Hz (zero) and 2083 1/3 Hz (one) tones. This offline reference
decoder is intended for deterministic testing and clean captures;
production streaming, clock recovery and RF noise handling follow later.
"""
from __future__ import annotations

import numpy as np

BAUD = 520.8333333333334
SPACE_HZ = 1562.5
MARK_HZ = 2083.3333333333335


def synthesize_same_audio(payload: bytes, sample_rate: int = 24000,
                          *, amplitude: float = 0.7) -> np.ndarray:
    """Generate continuous-phase AFSK with 8N1 framing for testing."""
    if sample_rate < 8000:
        raise ValueError("sample_rate must be at least 8000")
    if not 0 < amplitude <= 1:
        raise ValueError("amplitude must be in (0, 1]")
    bits = [1] * 20
    for byte in payload:
        bits.extend([0] + [(byte >> i) & 1 for i in range(8)] + [1])
    bits.extend([1] * 20)
    edges = np.rint(np.arange(len(bits) + 1) * sample_rate / BAUD).astype(int)
    frequencies = np.empty(edges[-1], dtype=np.float64)
    for index, bit in enumerate(bits):
        frequencies[edges[index]:edges[index + 1]] = MARK_HZ if bit else SPACE_HZ
    phase = 2 * np.pi * np.cumsum(frequencies) / sample_rate
    return (amplitude * np.sin(phase)).astype(np.float32)


def _classify_bits(audio: np.ndarray, sample_rate: int, offset: float) -> np.ndarray:
    """Noncoherent matched-tone energy per symbol, no phase assumptions."""
    count = int((len(audio) - offset) * BAUD / sample_rate)
    result = np.zeros(max(count, 0), dtype=np.uint8)
    for bit in range(count):
        start = int(round(offset + bit * sample_rate / BAUD))
        end = int(round(offset + (bit + 1) * sample_rate / BAUD))
        segment = audio[start:end]
        if len(segment) < 8:
            break
        t = np.arange(len(segment)) / sample_rate
        energies = []
        for frequency in (SPACE_HZ, MARK_HZ):
            projection = np.dot(segment, np.exp(-2j * np.pi * frequency * t))
            energies.append(abs(projection) ** 2)
        result[bit] = int(energies[1] > energies[0])
    return result


def _uart_bytes(bits: np.ndarray) -> bytes:
    """Recover 8N1 bytes, resynchronizing at each valid start bit."""
    output = bytearray()
    index = 0
    while index + 10 <= len(bits):
        if bits[index] == 0 and bits[index + 9] == 1:
            byte = sum(int(bits[index + 1 + k]) << k for k in range(8))
            output.append(byte)
            index += 10
        else:
            index += 1
    return bytes(output)


def decode_same_audio(audio: np.ndarray, sample_rate: int) -> bytes:
    """Return best candidate bytes from clean mono AFSK audio.

    A decoded candidate is NOT an authenticated warning. Use repeated-header
    validation before triggering any alert or receiver hold.
    """
    if sample_rate < 8000:
        raise ValueError("sample_rate must be at least 8000")
    samples = np.asarray(audio)
    if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.number):
        raise ValueError("audio must be mono numeric samples")
    if not np.all(np.isfinite(samples)):
        raise ValueError("audio must be finite")
    samples = samples.astype(np.float64, copy=False)
    if not len(samples):
        return b""
    symbol = sample_rate / BAUD
    best = b""
    best_score = -1
    for offset in np.arange(0, symbol, max(1, symbol / 12)):
        bits = _classify_bits(samples, sample_rate, float(offset))
        for bit_shift in range(10):
            candidate = _uart_bytes(bits[bit_shift:])
            score = (candidate.count(b"ZCZC") * 10000
                     + candidate.count(b"NNNN") * 10000
                     + sum(32 <= byte <= 126 for byte in candidate))
            if score > best_score:
                best, best_score = candidate, score
    return best
