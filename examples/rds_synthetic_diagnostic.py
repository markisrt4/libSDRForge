# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-free RDS receive-chain diagnostic using a known CRC-valid group.

Run: python examples/rds_synthetic_diagnostic.py
This is a diagnostic, not a claim that the full receiver passes validation.
"""
from __future__ import annotations

import numpy as np

from sdrforge.protocols.rds.rds_block_sync import encode_block
from sdrforge.protocols.rds.receiver_controller import RdsReceiverController

SAMPLE_RATE = 240_000
HALF_BIT_RATE = 2375
PI = 0x1234


def synthetic_multiplex(seconds: float = 4.0) -> np.ndarray:
    # A/B/C/D valid RDS group, repeated continuously.
    words = (encode_block(PI, "A"), encode_block(0x0400, "B"),
             encode_block(0, "C"), encode_block(0x4142, "D"))
    bits = [((word >> shift) & 1) for word in words for shift in range(25, -1, -1)]
    # Repeat the *data bits* before differential encoding. Repeating an already
    # encoded 104-bit waveform incorrectly resets differential state at every
    # group boundary and corrupts the first decoded bit of every group.
    count = int(seconds * SAMPLE_RATE)
    positions = np.floor(np.arange(count) * HALF_BIT_RATE / SAMPLE_RATE).astype(np.int64)
    total_bits = int(positions[-1] // 2) + 1 if count else 0
    data = np.resize(np.asarray(bits, dtype=np.uint8), total_bits)
    encoded = np.bitwise_xor.accumulate(data)
    half_index = positions // 2
    first_half = encoded[half_index]
    half_values = np.where((positions % 2) == 0, first_half, 1 - first_half)
    signs = 2 * half_values.astype(np.float32) - 1
    # No RF or FM discriminator here: inject directly into the 240 kSPS multiplex.
    # The idealized square envelope intentionally exercises extraction filtering.
    t = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    return (0.08 * signs * np.cos(2 * np.pi * 57_000 * t)).astype(np.float32)


def main() -> None:
    receiver = RdsReceiverController()
    multiplex = synthetic_multiplex()
    groups = []
    for offset in range(0, len(multiplex), 12000):
        groups.extend(receiver.process_multiplex(multiplex[offset:offset + 12000]))
    status = receiver.status
    print("Synthetic 57 kHz RDS diagnostic")
    print(f"Expected PI: 0x{PI:04X}")
    print(f"Validated groups: {len(groups)}")
    print(f"Recovered PI values: {[hex(g.pi) for g in groups[:5]]}")
    print(f"Phase groups: {status.phase_groups_found}")
    print(f"Invalid P0/P1: {status.phase_recent_invalid_pair_fraction}")
    print(f"Carrier offset: {status.carrier_offset_hz:+.1f} Hz")
    print(f"Half-bit period: {status.half_bit_samples_per_symbol:.4f} samples")
    print(f"RDS band excess: {status.rds_band_excess_db}")
    passed = any(group.pi == PI for group in groups)
    print("RESULT:", "PASS" if passed else "FAIL: full chain did not recover known-good group")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
