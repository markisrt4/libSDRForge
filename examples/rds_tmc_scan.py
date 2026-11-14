# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Inspect JSONL dumps of decoded RDS groups for potential TMC activity.

Each line contains pi, block_b, block_c, block_d (integers or hex strings).
This offline discovery tool does not tune hardware or decode traffic events.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.tmc_discovery import TmcDiscovery


def _word(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean is not an RDS word")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        result = int(value, 0)
    else:
        raise TypeError("RDS words must be integers or prefixed hex strings")
    if not 0 <= result <= 0xFFFF:
        raise ValueError("RDS word outside 16-bit range")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("groups", type=Path, help="JSONL of CRC-validated RDS groups")
    args = parser.parse_args()
    discovery = TmcDiscovery()
    with args.groups.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                group = RdsGroup(
                    pi=_word(item["pi"]),
                    block_b=_word(item["block_b"]),
                    block_c=_word(item["block_c"]),
                    block_d=_word(item["block_d"]),
                    c_prime=bool(item.get("c_prime", False)),
                )
                discovery.process(group)
            except (KeyError, TypeError, ValueError) as exc:
                parser.error(f"line {line_number}: {exc}")
    print(json.dumps(asdict(discovery.status), indent=2))
    print("8A groups are candidates, not proof of decodable traffic service.")


if __name__ == "__main__":
    main()
