"""!
@brief Experimental NOAA SAME AFSK demodulator for captured mono audio.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .same_messages import _HEADER

BAUD = 520.8333333333334
SPACE_HZ = 1562.5
MARK_HZ = 2083.3333333333335


def synthesize_same_audio(
    payload: bytes,
    sample_rate: int = 24000,
    *,
    amplitude: float = 0.7,
    baud: float = BAUD,
) -> np.ndarray:
    """!
    @brief Generate continuous-phase AFSK with 8N1 framing for testing.
    @param payload The payload value.
    @param sample_rate The sample rate value.
    @param amplitude The amplitude value.
    @param baud The baud value.
    @return The operation result.
    """
    if sample_rate < 8000:
        raise ValueError("sample_rate must be at least 8000")
    if not 0 < amplitude <= 1:
        raise ValueError("amplitude must be in (0, 1]")
    if not np.isfinite(baud) or baud <= 0 or baud > sample_rate / 8:
        raise ValueError("baud must be finite and allow at least 8 samples per symbol")
    bits = [1] * 20
    for byte in payload:
        bits.extend([0] + [(byte >> i) & 1 for i in range(8)] + [1])
    bits.extend([1] * 20)
    edges = np.rint(np.arange(len(bits) + 1) * sample_rate / baud).astype(int)
    frequencies = np.empty(edges[-1], dtype=np.float64)
    for index, bit in enumerate(bits):
        frequencies[edges[index] : edges[index + 1]] = MARK_HZ if bit else SPACE_HZ
    phase = 2 * np.pi * np.cumsum(frequencies) / sample_rate
    return (amplitude * np.sin(phase)).astype(np.float32)


def _classify_bits(
    audio: np.ndarray, sample_rate: int, offset: float, baud: float = BAUD
) -> np.ndarray:
    """Noncoherent matched-tone energy per symbol, no phase assumptions."""
    count = int((len(audio) - offset) * baud / sample_rate)
    result = np.zeros(max(count, 0), dtype=np.uint8)
    for bit in range(count):
        start = round(offset + bit * sample_rate / baud)
        end = round(offset + (bit + 1) * sample_rate / baud)
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


def _symbol_confidences(
    audio: np.ndarray, sample_rate: int, offset: float, baud: float = BAUD
) -> np.ndarray:
    """Signed normalized mark-minus-space energies, one value per symbol.

    Positive means mark (1), negative means space (0). Values near zero
    indicate an ambiguous decision. These are not calibrated probabilities.
    """
    count = max(0, int((len(audio) - offset) * baud / sample_rate))
    result = np.zeros(count, dtype=np.float64)
    for bit in range(count):
        start = round(offset + bit * sample_rate / baud)
        end = round(offset + (bit + 1) * sample_rate / baud)
        segment = audio[start:end]
        if len(segment) < 8:
            break
        t = np.arange(len(segment)) / sample_rate
        space = abs(np.dot(segment, np.exp(-2j * np.pi * SPACE_HZ * t))) ** 2
        mark = abs(np.dot(segment, np.exp(-2j * np.pi * MARK_HZ * t))) ** 2
        result[bit] = (mark - space) / (mark + space + 1e-12)
    return result


def _uart_confidence(metrics: np.ndarray) -> float:
    """Average confidence of UART framing and data decisions.

    Uses observed magnitudes, not any assumed header payload. Start/stop
    symbols must agree with UART framing. No bits are corrected here.
    """
    index = 0
    confidence: list[float] = []
    while index + 10 <= len(metrics):
        if metrics[index] < 0 and metrics[index + 9] > 0:
            frame = metrics[index : index + 10]
            confidence.extend(float(value) for value in np.abs(frame))
            index += 10
        else:
            index += 1
    return float(np.mean(confidence)) if confidence else 0.0


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


def _candidate_score(candidate: bytes) -> tuple[int, int, int, int]:
    """Rank structurally complete headers above partial sync words.

    This is candidate ranking only, NOT repeated-header alert confirmation.
    Avoid treating incidental printable bytes as equivalent to a valid header.
    """
    headers = tuple(_HEADER.finditer(candidate))
    complete_bytes = sum(len(match.group()) for match in headers)
    return (
        len(headers),
        complete_bytes,
        candidate.count(b"ZCZC") + candidate.count(b"NNNN"),
        sum(32 <= byte <= 126 for byte in candidate),
    )


@dataclass(frozen=True)
class SameDecodeResult:
    """!
    @brief Provide SameDecodeResult behavior.
    """

    data: bytes
    baud_offset: float
    sample_offset: float
    bit_shift: int
    complete_headers: int
    decision_confidence: float = 0.0


def decode_same_audio_diagnostic(
    audio: np.ndarray, sample_rate: int, *, baud_offsets: tuple[float, ...] = (0.0,)
) -> SameDecodeResult:
    """!
    @brief Return selected candidate and clock hypothesis for diagnostics.
    @param audio The audio value.
    @param sample_rate The sample rate value.
    @param baud_offsets The baud offsets value.
    @return The operation result.
    """
    if sample_rate < 8000:
        raise ValueError("sample_rate must be at least 8000")
    if not baud_offsets or any(
        not np.isfinite(delta) or BAUD + delta <= 0 for delta in baud_offsets
    ):
        raise ValueError("baud_offsets must contain finite positive resulting rates")
    samples = np.asarray(audio)
    if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.number):
        raise ValueError("audio must be mono numeric samples")
    if not np.all(np.isfinite(samples)):
        raise ValueError("audio must be finite")
    samples = samples.astype(np.float64, copy=False)
    if not len(samples):
        return SameDecodeResult(b"", 0.0, 0.0, 0, 0)
    best = b""
    selected = (0.0, 0.0, 0)
    best_score = (-1, -1, -1, -1)
    best_confidence = 0.0
    # Structural evidence always outranks confidence; confidence only breaks
    # ties in the same structural tier (complete headers and sync markers).
    # Search candidate symbol clocks independently. Small transmitter/receiver
    # clock errors accumulate over long SAME headers; the nominal clock alone
    # can eventually slip a full bit. Default preserves legacy performance.
    for delta in baud_offsets:
        baud = BAUD + delta
        symbol = sample_rate / baud
        for offset in np.arange(0, symbol, max(1, symbol / 12)):
            bits = _classify_bits(samples, sample_rate, float(offset), baud)
            for bit_shift in range(10):
                candidate = _uart_bytes(bits[bit_shift:])
                score = _candidate_score(candidate)
                structural = score[:3]
                previous_structural = best_score[:3]
                # Preserve existing full-header and synchronization priority.
                # For equally plausible structural candidates, use soft
                # confidence before printable-byte count.
                if structural < previous_structural:
                    continue
                metrics = _symbol_confidences(samples, sample_rate, float(offset), baud)
                confidence = _uart_confidence(metrics[bit_shift:])
                if (structural, confidence, score[3]) > (
                    previous_structural,
                    best_confidence,
                    best_score[3],
                ):
                    best, best_score = candidate, score
                    selected = (float(delta), float(offset), bit_shift)
                    best_confidence = confidence
    return SameDecodeResult(best, *selected, best_score[0], best_confidence)


def decode_same_audio(
    audio: np.ndarray, sample_rate: int, *, baud_offsets: tuple[float, ...] = (0.0,)
) -> bytes:
    """!
    @brief Return decoded bytes; candidates are NOT validated emergency alerts.
    @param audio The audio value.
    @param sample_rate The sample rate value.
    @param baud_offsets The baud offsets value.
    @return The operation result.
    """
    return decode_same_audio_diagnostic(
        audio, sample_rate, baud_offsets=baud_offsets
    ).data
