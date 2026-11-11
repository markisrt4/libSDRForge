# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-free RDS CRC and four-block synchronization tests."""

import unittest
from itertools import chain

import numpy as np

from sdrforge.protocols.rds.rds_block_sync import (
    OFFSET_WORDS,
    RdsBlockSynchronizer,
    decode_block,
    encode_block,
    syndrome,
)


def bits_of(word):
    return [(word >> shift) & 1 for shift in range(25, -1, -1)]


def group_bits(pi=0x1234, b=0x0A35, c=0xBEEF, d=0x4D52, c_prime=False):
    names = ("A", "B", "C_prime" if c_prime else "C", "D")
    return np.asarray(list(chain.from_iterable(bits_of(encode_block(data, name))
                           for data, name in zip((pi, b, c, d), names))),
                      dtype=np.uint8)


class RdsBlockSyncTest(unittest.TestCase):
    def test_offset_words_and_round_trip(self):
        for name, offset in OFFSET_WORDS.items():
            for data in (0, 0x1234, 0xFFFF):
                word = encode_block(data, name)
                self.assertEqual(syndrome(word), offset)
                self.assertEqual(decode_block(word), (name, data))
                self.assertEqual(decode_block(word, name), (name, data))
                self.assertIsNone(decode_block(word ^ 1, name))

    def test_group_and_c_prime(self):
        receiver = RdsBlockSynchronizer()
        found = receiver.process(np.concatenate((group_bits(),
                                                  group_bits(c_prime=True))))
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].pi, 0x1234)
        self.assertEqual(found[0].block_c, 0xBEEF)
        self.assertFalse(found[0].c_prime)
        self.assertTrue(found[1].c_prime)
        self.assertEqual(receiver.groups_found, 2)

    def test_acquisition_and_irregular_chunks(self):
        stream = np.concatenate((np.array([1, 0, 1, 1, 0, 0, 1],
                                          dtype=np.uint8), group_bits(),
                                 group_bits(c_prime=True)))
        whole = RdsBlockSynchronizer().process(stream)
        receiver = RdsBlockSynchronizer()
        pieces = [receiver.process(stream[i:i + 17])
                  for i in range(0, len(stream), 17)]
        self.assertEqual(list(chain.from_iterable(pieces)), whole)

    def test_corruption_and_erasures(self):
        first = group_bits()
        damaged = first.copy()
        damaged[34] ^= 1
        receiver = RdsBlockSynchronizer()
        found = receiver.process(np.concatenate((damaged, first)))
        self.assertEqual(len(found), 1)
        flags = np.ones(104, dtype=bool)
        flags[40] = False
        receiver.reset()
        self.assertEqual(receiver.process(first, flags), [])
        self.assertEqual(len(receiver.process(first)), 1)

    def test_reject_invalid_inputs(self):
        with self.assertRaises(ValueError):
            encode_block(0x10000, "A")
        with self.assertRaises(ValueError):
            encode_block(10, "Z")
        with self.assertRaises(ValueError):
            syndrome(-1)
        with self.assertRaises(ValueError):
            decode_block(encode_block(0, "A"), "Z")
        receiver = RdsBlockSynchronizer()
        for bad in (np.array([2]), np.ones((2, 2))):
            with self.assertRaises(ValueError):
                receiver.process(bad)
        with self.assertRaises(ValueError):
            receiver.process(np.array([0, 1]), np.array([True]))


if __name__ == "__main__":
    unittest.main()
