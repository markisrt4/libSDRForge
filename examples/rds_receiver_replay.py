# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Replay recorded RTL IQ through the integrated strict and experimental RDS paths."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.receiver_controller import RdsReceiverController


def replay(path: Path, seconds: float) -> dict:
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("expected 2.4 MSPS RTL unsigned IQ")
    if meta.get("gaps"):
        raise ValueError("IQ recording has gaps")
    center = int(meta["center_frequency_hz"])
    ddc = DigitalDownconverter()
    receiver = RdsReceiverController(experimental_soft_pairs=True)
    strict = 0
    soft = Counter()
    uncertain = Counter()
    confirmed = {}
    processed = 0
    limit = round(seconds * 2_400_000)
    with path.open("rb") as stream:
        while processed < limit:
            raw = stream.read(min(262144, 2 * (limit - processed)))
            if not raw:
                break
            if len(raw) % 2:
                raise ValueError("incomplete IQ pair")
            block = IqBlock(samples=raw, center_frequency_hz=center,
                            sample_rate_hz=2_400_000, timestamp_ns=0)
            groups = receiver.process_iq(ddc.process(block, center))
            strict += len(groups)
            for group in receiver.experimental_soft_last_groups:
                key = (group.pi, (group.block_b >> 12) & 15)
                soft[key] += 1
                uncertain[group.uncertain_bits] += 1
            for fragment in receiver.experimental_confirmed_fragments:
                key = (fragment.pi, fragment.ab_flag, fragment.segment)
                confirmed[key] = {
                    "pi": f"0x{fragment.pi:04X}", "ab": fragment.ab_flag,
                    "segment": fragment.segment, "text": fragment.text,
                    "observations": fragment.observations,
                }
            processed += len(raw) // 2
    return {
        "seconds_processed": processed / 2_400_000,
        "strict_groups": strict,
        "experimental_groups_by_pi_type": [
            {"pi": f"0x{pi:04X}", "type": kind, "count": count}
            for (pi, kind), count in sorted(soft.items())],
        "experimental_uncertain_bits_histogram": dict(sorted(uncertain.items())),
        "confirmed_experimental_fragments": list(confirmed.values()),
        "experimental_radio_text": [
            {"pi": f"0x{item.pi:04X}" if item.pi is not None else None,
             "ab": item.ab_flag, "preview": item.preview,
             "confirmed_segments": item.confirmed_segments,
             "missing_segments": list(item.missing_segments),
             "conflicted_segments": list(item.conflicted_segments),
             "complete": item.complete, "observations": list(item.observations)}
            for item in receiver.experimental_radio_text],
        "trusted_metadata": {
            "pi": receiver.status.metadata.pi,
            "program_service": receiver.status.metadata.program_service,
            "radio_text": receiver.status.metadata.radio_text,
        },
        "note": "Experimental fragments are corroborated candidates, not trusted TMC.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iq", type=Path)
    parser.add_argument("--seconds", type=float, default=20.0)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    print(json.dumps(replay(args.iq, args.seconds), indent=2))


if __name__ == "__main__":
    main()
