# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Inspect complete ALERT-C 8A group patterns without guessing incident data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from sdrforge.protocols.rds.alert_c_8a import parse_alert_c_8a, to_dict
from sdrforge.protocols.rds.rds_block_sync import RdsGroup


def analyze(path: Path) -> dict:
    groups: list[dict] = []
    partial = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("group") != "8A":
            continue
        words = str(record.get("raw_data", "")).split()
        if len(words) != 4 or any(len(word) != 4 for word in words) or "----" in words:
            partial += 1
            continue
        try:
            a, b, c, d = [int(word, 16) for word in words]
        except ValueError:
            partial += 1
            continue
        if a > 0xFFFF or b > 0xFFFF or c > 0xFFFF or d > 0xFFFF or (b >> 12) != 8 or (b & 0x0800):
            partial += 1
            continue
        groups.append({"pi": f"{a:04X}", "b": f"{b:04X}", "c": f"{c:04X}", "d": f"{d:04X}",
                       "x": (b >> 4) & 1, "continuity_index": b & 7,
                       "raw": " ".join(words)})
    decoded = [to_dict(parse_alert_c_8a(RdsGroup(
        int(item["pi"], 16), int(item["b"], 16),
        int(item["c"], 16), int(item["d"], 16), False,
        synchronization="redsea_fec_unknown",
    ))) for item in groups]
    repeated = Counter(item["raw"] for item in groups)
    by_ci: dict[str, list[str]] = defaultdict(list)
    for item in groups:
        by_ci[str(item["continuity_index"])].append(item["raw"])
    return {"complete": len(groups), "partial": partial, "unique": len(repeated),
            "x_bit_counts": dict(Counter(item["x"] for item in groups)),
            "continuity_index_counts": dict(Counter(item["continuity_index"] for item in groups)),
            "message_kinds": dict(Counter(item["kind"] for item in decoded)),
            "decoded_structure": decoded,
            "repeated_groups": [{"count": count, "raw": raw} for raw, count in repeated.most_common()],
            "groups_by_continuity_index": dict(by_ci),
            "warning": "Structural diagnostics only. No decrypted location or validated incident inferred."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path, help="redsea newline-delimited JSON capture")
    args = parser.parse_args()
    print(json.dumps(analyze(args.jsonl), indent=2))


if __name__ == "__main__":
    main()
