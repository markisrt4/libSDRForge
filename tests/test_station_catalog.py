# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Persistent station catalog trust and reload tests."""

import tempfile
import unittest
from pathlib import Path

from sdrforge.protocols.rds.station_catalog import StationCatalog


class StationCatalogTest(unittest.TestCase):
    def test_experimental_identity_never_promotes_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stations.json"
            catalog = StationCatalog(path)
            catalog.observe(frequency_hz=94700000, pi=0x5BDB, verified=False,
                            program_service="UNTRUSTED")
            catalog.save()
            entry = next(iter(StationCatalog(path).stations.values()))
            self.assertFalse(entry["verified"])
            self.assertIsNone(entry["program_service"])
            self.assertEqual(entry["experimental_observations"], 1)
            catalog.observe(frequency_hz=94700000, pi=0x5BDB, verified=True,
                            program_service="WXYZ")
            catalog.save()
            entry = next(iter(StationCatalog(path).stations.values()))
            self.assertTrue(entry["verified"])
            self.assertEqual(entry["program_service"], "WXYZ")
            self.assertEqual(entry["observations"], 1)

    def test_frequency_is_part_of_station_key(self):
        catalog = StationCatalog(Path("unused-test-catalog.json"))
        catalog.observe(frequency_hz=94700000, pi=0x5BDB, verified=False)
        catalog.observe(frequency_hz=93100000, pi=0x5BDB, verified=False)
        self.assertEqual(len(catalog.stations), 2)


if __name__ == "__main__":
    unittest.main()
