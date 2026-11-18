# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-free redsea adapter regression tests."""
import unittest

import numpy as np

from sdrforge.protocols.rds.redsea_adapter import (
    multiplex_to_pcm,
    parse_redsea_line,
)
from sdrforge.protocols.rds.tmc_discovery import TmcDiscovery


class RedseaAdapterTest(unittest.TestCase):
    def test_complete_tmc_group_preserves_provenance(self) -> None:
        record = parse_redsea_line(
            '{"group":"8A","pi":"0x7ADA",'
            '"raw_data":"7ADA 80E2 C323 7837"}'
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertIsNotNone(record.group)
        assert record.group is not None
        self.assertEqual(record.group.pi, 0x7ADA)
        self.assertEqual(record.group.block_c, 0xC323)
        self.assertEqual(record.group.synchronization, "redsea_fec_unknown")
        discovery = TmcDiscovery()
        discovery.process(record.group)
        self.assertEqual(discovery.status.group_8a_count, 0)

    def test_partial_group_not_validated(self) -> None:
        record = parse_redsea_line(
            '{"group":"8A","raw_data":"7ADA 80E2 ---- ----"}'
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertIsNone(record.group)

    def test_malformed_and_non_group_records(self) -> None:
        self.assertIsNone(parse_redsea_line("not json"))
        self.assertIsNone(parse_redsea_line("[]"))
        self.assertIsNone(parse_redsea_line('{"group":"8A","raw_data":"7ADA 80E2 GG00 7837"}').group)
        self.assertIsNone(parse_redsea_line('{"group":"3A","raw_data":"7ADA 80E2 C323 7837"}').group)

    def test_pcm_conversion(self) -> None:
        data = multiplex_to_pcm(np.array([-1.0, 0.0, 1.0], dtype=np.float32))
        self.assertEqual(np.frombuffer(data, dtype="<i2").tolist(),
                         [-6553, 0, 6553])
        with self.assertRaises(ValueError):
            multiplex_to_pcm(np.array([float("nan")]))


if __name__ == "__main__":
    unittest.main()
