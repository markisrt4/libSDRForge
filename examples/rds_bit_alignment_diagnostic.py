# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Compare synthetic recovered RDS bits with known transmit bits, allowing delay."""
from __future__ import annotations

import numpy as np
from rds_synthetic_diagnostic import PI, synthetic_multiplex
from sdrforge.protocols.rds.rds_block_sync import encode_block
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder


def main() -> None:
    words = [encode_block(PI, "A"), encode_block(0x0400, "B"),
             encode_block(0, "C"), encode_block(0x4142, "D")]
    expected = np.array([(w >> i) & 1 for w in words for i in range(25, -1, -1)],
                        dtype=np.uint8)
    multiplex = synthetic_multiplex()
    extractor = RdsSubcarrierExtractor()
    timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
    recovered = []
    for start in range(0, len(multiplex), 12000):
        recovered.append(timing.process(extractor.process(multiplex[start:start + 12000])))
    halves = np.concatenate(recovered)
    print(f"Recovered half-bits: {len(halves)}; expected periodic bits: {len(expected)}")
    for phase in (0, 1):
        decoder = RdsBiphaseDecoder(pair_phase=phase)
        bits, valid = decoder.process(halves)
        # Search the full periodic group for delay and possible inverted data polarity.
        best = None
        for shift in range(len(expected)):
            reference = expected[(np.arange(len(bits)) + shift) % len(expected)]
            for inversion in (0, 1):
                matches = valid & (bits == (reference ^ inversion))
                fraction = float(np.sum(matches) / max(np.sum(valid), 1))
                candidate = (fraction, shift, inversion)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        assert best is not None
        print(f"Phase {phase}: valid={np.sum(valid)}/{len(bits)} "
              f"best_match={best[0]:.2%} shift={best[1]} inverted={bool(best[2])}")
        print("  first 64 recovered:", "".join(map(str, bits[:64])))
        reference = expected[(np.arange(64) + best[1]) % len(expected)] ^ best[2]
        print("  first 64 expected: ", "".join(map(str, reference)))
    print("A near-100% match with nonzero shift indicates alignment, not random bits.")


if __name__ == "__main__":
    main()
