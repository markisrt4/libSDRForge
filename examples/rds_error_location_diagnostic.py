"""Locate synthetic RDS bit errors and CRC-clean group windows."""
from __future__ import annotations

import numpy as np

from rds_synthetic_diagnostic import PI, synthetic_multiplex
from sdrforge.protocols.rds.rds_block_sync import encode_block
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer


def main() -> None:
    words = [encode_block(PI, "A"), encode_block(0x0400, "B"),
             encode_block(0, "C"), encode_block(0x4142, "D")]
    expected = np.asarray([(w >> i) & 1 for w in words for i in range(25, -1, -1)], dtype=np.uint8)
    extractor = RdsSubcarrierExtractor()
    timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
    halves = []
    multiplex = synthetic_multiplex()
    for start in range(0, len(multiplex), 12000):
        halves.append(timing.process(extractor.process(multiplex[start:start + 12000])))
    recovered = np.concatenate(halves)
    for phase in (0, 1):
        decoder = RdsBiphaseDecoder(pair_phase=phase)
        bits, valid = decoder.process(recovered)
        reference = expected[np.arange(len(bits)) % len(expected)]
        errors = (~valid) | (bits != reference)
        mismatch = valid & (bits != reference)
        print(f"Phase {phase}: bits={len(bits)} valid={np.count_nonzero(valid)} "
              f"mismatches={np.count_nonzero(mismatch)} erasures={np.count_nonzero(~valid)}")
        print("First 40 error/erasure indices:", np.flatnonzero(errors)[:40].tolist())
        # The first bit after a decoder reset is necessarily an erasure.
        full = len(bits) // 104
        clean = [g for g in range(full) if not errors[g * 104:(g + 1) * 104].any()]
        print(f"CRC-clean aligned 104-bit groups: {len(clean)}/{full}; first={clean[:20]}")
        print("Errors per 104-bit group (first 20):",
              [int(errors[g*104:(g+1)*104].sum()) for g in range(min(full,20))])
        sync = RdsBlockSynchronizer()
        groups = sync.process(bits, valid)
        print(f"Synchronizer groups: {len(groups)}; matching PI: {sum(g.pi == PI for g in groups)}")
    print("Note: this diagnostic assumes no bit insertion/deletion; index drift would change alignment.")


if __name__ == "__main__":
    main()
