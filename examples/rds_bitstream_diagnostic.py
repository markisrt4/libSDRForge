# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Isolate RDS biphase/differential decoding from RF and carrier recovery."""
from __future__ import annotations

import numpy as np

from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import (
    RdsBlockSynchronizer, decode_block, encode_block,
)

PI = 0x1234


def main() -> None:
    words = [encode_block(PI, "A"), encode_block(0x0400, "B"),
             encode_block(0, "C"), encode_block(0x4142, "D")]
    expected = np.asarray([(word >> shift) & 1 for word in words
                           for shift in range(25, -1, -1)], dtype=np.uint8)
    assert all(decode_block(word, name) is not None
               for word, name in zip(words, ("A", "B", "C", "D")))
    print("Expected first 32 bits:", "".join(map(str, expected[:32])))
    for invert in (False, True):
        previous = 0
        halves = []
        for bit in np.tile(expected, 8):
            previous ^= int(bit)
            halves.extend((previous, 1 - previous))
        decoder = RdsBiphaseDecoder(pair_phase=0, invert=invert)
        decoded, valid = decoder.process(np.asarray(halves, dtype=np.float32) * 2 - 1)
        sync = RdsBlockSynchronizer()
        groups = sync.process(decoded, valid)
        mismatch = int(np.count_nonzero(decoded[1:len(expected)] != expected[1:]))
        print(f"invert={invert}: invalid_pairs={decoder.invalid_pairs}, "
              f"bit_mismatches_after_first={mismatch}/{len(expected) - 1}, "
              f"groups={len(groups)}, PIs={[hex(g.pi) for g in groups[:3]]}")
        if groups and any(g.pi == PI for g in groups):
            print("PASS: biphase + CRC pipeline")
            return
    print("FAIL: known-good bits not recovered through biphase + CRC")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
