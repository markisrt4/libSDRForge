# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Experimental full-chain synthetic RDS multiplex regression.

No DSP stage is stubbed. This test deliberately exposes acquisition failures
rather than assuming component-level tests imply successful RDS reception.
"""

import unittest

import numpy as np

from sdrforge.protocols.rds.receiver_controller import RdsReceiverController

SAMPLE_RATE = 240_000
BIT_RATE = 1187.5


def independent_checkword(data: int, offset: int) -> int:
    """Reference long-division implementation, separate from receiver code."""
    polynomial = 0b10110111001
    dividend = data << 10
    for position in range(25, 9, -1):
        if dividend & (1 << position):
            dividend ^= polynomial << (position - 10)
    return (data << 10) | ((dividend & 1023) ^ offset)


def ps_group(index: int, pair: str, pi: int = 0x4961) -> list[int]:
    payload = (pi, index, 0, (ord(pair[0]) << 8) | ord(pair[1]))
    offsets = (0x0FC, 0x198, 0x168, 0x1B4)
    return [independent_checkword(data, offset)
            for data, offset in zip(payload, offsets)]


def waveform(*, cycles: int = 4, noise: float = 0.0,
             carrier_offset_hz: float = 0.0, seed: int = 4961) -> np.ndarray:
    """Build a 240 kSPS FM multiplex with biphase RDS at 57 kHz.

    This is a simplified shaped baseband waveform, not a complete EN 50067
    compliant transmitter. Pilot and mono tones are included as interferers.
    """
    rng = np.random.default_rng(seed)
    groups = []
    for _ in range(cycles):
        for index, pair in enumerate(("OR", "C ", "FM", "  ")):
            groups.extend(ps_group(index, pair))
    bits = np.asarray([(word >> shift) & 1
                       for word in groups for shift in range(25, -1, -1)],
                      dtype=np.uint8)
    # Differentially encode each bit; each bit has two opposite half-bits.
    previous = 0
    halves = []
    for bit in bits:
        previous ^= int(bit)
        halves.extend((2 * previous - 1, 1 - 2 * previous))
    halves = np.asarray(halves, dtype=np.float64)
    count = int((len(halves) + 8) * SAMPLE_RATE / (2 * BIT_RATE))
    t = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    half_positions = t * (2 * BIT_RATE)
    shaped = np.interp(half_positions, np.arange(len(halves)) + 0.5,
                       halves, left=halves[0], right=0.0)
    multiplex = (0.22 * shaped *
                 np.cos(2 * np.pi * (57_000 + carrier_offset_hz) * t + 0.15)
                 + 0.08 * np.sin(2 * np.pi * 19_000 * t)
                 + 0.12 * np.sin(2 * np.pi * 1_000 * t))
    if noise:
        multiplex += rng.normal(0, noise, size=count)
    return multiplex.astype(np.float32)


class RdsEndToEndWaveformTest(unittest.TestCase):
    def test_reference_crc_vector(self):
        # Known 16-bit payload and expected offset are checked independently
        # of the production encoder.
        from sdrforge.protocols.rds.rds_block_sync import syndrome
        self.assertEqual(syndrome(independent_checkword(0x4961, 0x0FC)),
                         0x0FC)

    def test_full_multiplex_to_station_name(self):
        receiver = RdsReceiverController()
        samples = waveform()
        for start in range(0, len(samples), 8191):
            receiver.process_multiplex(samples[start:start + 8191])
        self.assertGreater(receiver.status.groups_found, 0,
                           f"RDS acquisition failed: {receiver.status}")
        self.assertEqual(receiver.status.metadata.pi, 0x4961)
        self.assertEqual(receiver.status.metadata.program_service, "ORC FM")


if __name__ == "__main__":
    unittest.main()
