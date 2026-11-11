# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Find the first failing stage of the synthetic RDS receive chain."""
from __future__ import annotations

import numpy as np

from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer
from rds_synthetic_diagnostic import PI, synthetic_multiplex


def evaluate(name: str, symbols: np.ndarray) -> None:
    print(f"\\n{name}: symbols={len(symbols)}")
    for phase in (0, 1):
        decoder = RdsBiphaseDecoder(pair_phase=phase)
        bits, valid = decoder.process(symbols)
        groups = RdsBlockSynchronizer().process(bits, valid)
        print(f"  phase={phase} invalid={decoder.invalid_pairs}/{decoder.total_pairs} "
              f"valid_groups={len(groups)} correct_PI={sum(g.pi == PI for g in groups)}")


def main() -> None:
    signal = synthetic_multiplex()
    extractor = RdsSubcarrierExtractor()
    carrier = RdsCarrierRecovery()
    timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
    raw = []
    corrected = []
    recovered = []
    for offset in range(0, len(signal), 12000):
        baseband = extractor.process(signal[offset:offset + 12000])
        rotated = carrier.process(baseband)
        raw.append(baseband)
        corrected.append(rotated)
        recovered.append(timing.process(rotated))
    baseband = np.concatenate(raw)
    rotated = np.concatenate(corrected)
    halves = np.concatenate(recovered)
    print(f"Baseband RMS: {np.sqrt(np.mean(np.abs(baseband)**2)):.5f}")
    print(f"Carrier offset: {carrier.frequency_offset_hz:+.2f} Hz")
    print(f"Half-bit period: {timing.samples_per_symbol:.5f}")
    evaluate("Full extractor + carrier + timing", halves)
    # Ideal carrier at zero offset: compare without the Costas loop.
    ideal_timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
    evaluate("Extractor + timing (bypass Costas)", ideal_timing.process(baseband))
    # Test the same timing recovery on an ideal 12 kSPS baseband waveform.
    count = len(baseband)
    t = np.arange(count, dtype=np.float64) / 12000.0
    words = __import__("sdrforge.protocols.rds.rds_block_sync", fromlist=["encode_block"]).encode_block
    payload = [words(PI, "A"), words(0x0400, "B"), words(0, "C"), words(0x4142, "D")]
    bits = [(word >> shift) & 1 for word in payload for shift in range(25, -1, -1)]
    previous = 0
    halfbits = []
    for bit in bits:
        previous ^= bit
        halfbits.extend((previous, 1 - previous))
    signs = np.asarray(halfbits, dtype=np.float32) * 2 - 1
    ideal = signs[(np.floor(t * 2375).astype(np.int64)) % len(signs)].astype(np.complex64)
    ideal_timing2 = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
    evaluate("Ideal baseband + timing (bypass extraction and Costas)", ideal_timing2.process(ideal))


if __name__ == "__main__":
    main()
