# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Replay a redsea JSONL capture through the live WBFM ALERT-C ingestion path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sdrforge.protocols.rds.redsea_adapter import parse_redsea_line
from sdrforge.receivers.wbfm_receiver import WbfmReceiver


def replay(path: Path) -> dict:
    receiver = WbfmReceiver(channel_frequency_hz=104_300_000, rds_enabled=True)
    accepted = 0
    rejected = 0
    try:
        with path.open(encoding="utf-8") as capture:
            for line in capture:
                record = parse_redsea_line(line)
                if record is None or record.group is None:
                    rejected += 1
                    continue
                if (record.group.block_b >> 12) != 8 or record.group.block_b & 0x0800:
                    continue
                receiver.ingest_rds_groups((record.group,))
                accepted += 1
        return {
            "replayed_8a_groups": accepted,
            "invalid_or_partial_records": rejected,
            "assembly_candidates": receiver.tmc_candidate_report,
        }
    finally:
        receiver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.capture), indent=2))


if __name__ == "__main__":
    main()
