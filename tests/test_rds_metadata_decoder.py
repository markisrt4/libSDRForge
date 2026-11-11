# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Independent synthetic RDS metadata group assembly tests."""

import unittest

from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.rds_metadata_decoder import RdsMetadataDecoder


def word(text):
    assert len(text) == 2
    return (ord(text[0]) << 8) | ord(text[1])


def ps(index, text, pi=0x1234, version_b=False):
    return RdsGroup(pi, (0x0800 if version_b else 0) | index,
                    0, word(text), version_b)


def rt(index, text, pi=0x1234, ab=0, version_b=False):
    b = 0x2000 | (0x0800 if version_b else 0) | (ab << 4) | index
    if version_b:
        return RdsGroup(pi, b, 0, word(text), True)
    return RdsGroup(pi, b, word(text[:2]), word(text[2:]), False)


class RdsMetadataDecoderTest(unittest.TestCase):
    def test_out_of_order_ps_and_duplicates(self):
        decoder = RdsMetadataDecoder()
        for index, text in ((2, "FM"), (0, "OR"), (2, "FM"), (3, "  ")):
            result = decoder.process(ps(index, text))
            self.assertIsNone(result.program_service)
        self.assertEqual(decoder.process(ps(1, "C ")).program_service, "ORC FM")
        self.assertEqual(decoder.metadata.pi, 0x1234)

    def test_station_change_resets_text(self):
        decoder = RdsMetadataDecoder()
        for i, segment in enumerate(("AB", "CD", "EF", "GH")):
            decoder.process(ps(i, segment))
        self.assertEqual(decoder.metadata.program_service, "ABCDEFGH")
        changed = decoder.process(ps(0, "XY", pi=0x4321))
        self.assertEqual(changed.pi, 0x4321)
        self.assertIsNone(changed.program_service)

    def test_2a_radiotext_with_terminator(self):
        decoder = RdsMetadataDecoder()
        self.assertIsNone(decoder.process(rt(1, "RLD!")).radio_text)
        decoder.process(rt(0, "HELL"))
        result = decoder.process(rt(2, " ORC"))
        self.assertIsNone(result.radio_text)
        result = decoder.process(rt(3, " FM\r"))
        self.assertEqual(result.radio_text, "HELLRLD! ORC FM")

    def test_2b_radiotext_and_ab_toggle(self):
        decoder = RdsMetadataDecoder()
        for i, segment in enumerate(("HI", "!!", "\r ")):
            result = decoder.process(rt(i, segment, version_b=True))
        self.assertEqual(result.radio_text, "HI!!")
        self.assertIsNone(decoder.process(rt(0, "NO", ab=1, version_b=True)).radio_text)
        self.assertEqual(decoder.process(rt(1, "\r ", ab=1, version_b=True)).radio_text, "NO")

    def test_partial_text_is_not_published(self):
        decoder = RdsMetadataDecoder()
        decoder.process(ps(0, "AB"))
        decoder.process(ps(1, "CD"))
        self.assertIsNone(decoder.metadata.program_service)
        decoder.process(rt(0, "TEST"))
        decoder.process(rt(2, "\r   "))
        self.assertIsNone(decoder.metadata.radio_text)

    def test_repeated_segments_filter_single_corruption(self):
        decoder = RdsMetadataDecoder(ps_repetitions=2)
        for i, segment in enumerate(("WO", "MC", "10", "4 ")):
            decoder.process(ps(i, segment))
        self.assertIsNone(decoder.metadata.program_service)
        decoder.process(ps(0, "XX"))
        for i, segment in enumerate(("WO", "MC", "10", "4 ")):
            decoder.process(ps(i, segment))
        self.assertIsNone(decoder.metadata.program_service)
        self.assertEqual(decoder.process(ps(0, "WO")).program_service, "WOMC104")

    def test_sync_loss_retains_published_metadata(self):
        decoder = RdsMetadataDecoder(ps_repetitions=2)
        for _ in range(2):
            for i, segment in enumerate(("WO", "MC", "10", "4 ")):
                decoder.process(ps(i, segment))
        before = decoder.metadata
        decoder.lose_sync()
        self.assertEqual(decoder.metadata, before)
        decoder.process(ps(0, "ZZ"))
        self.assertEqual(decoder.metadata, before)

    def test_invalid_repetition_count(self):
        with self.assertRaises(ValueError):
            RdsMetadataDecoder(ps_repetitions=0)

    def test_rejects_non_group(self):
        with self.assertRaises(TypeError):
            RdsMetadataDecoder().process(None)


if __name__ == "__main__":
    unittest.main()
