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
from sdrforge.protocols.rds.station_catalog import StationCatalog


def replay(path: Path, seconds: float, catalog: StationCatalog | None = None,
           *, persistent_sync: bool = False,
           extractor_cutoff_hz: float = 3_000.0) -> dict:
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("expected 2.4 MSPS RTL unsigned IQ")
    if meta.get("gaps"):
        raise ValueError("IQ recording has gaps")
    center = int(meta["center_frequency_hz"])
    ddc = DigitalDownconverter()
    receiver = RdsReceiverController(experimental_soft_pairs=True,
                                     persistent_sync=persistent_sync,
                                     extractor_cutoff_hz=extractor_cutoff_hz)
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
    if catalog is not None:
        if receiver.status.metadata.pi is not None:
            catalog.observe(frequency_hz=center, pi=receiver.status.metadata.pi,
                            verified=True,
                            program_service=receiver.status.metadata.program_service)
        for item in receiver.experimental_radio_text:
            if item.pi is not None and item.confirmed_segments:
                catalog.observe(frequency_hz=center, pi=item.pi, verified=False)
        catalog.save()
    return {
        "persistent_sync_enabled": receiver.status.persistent_sync_enabled,
        "extractor_cutoff_hz": extractor_cutoff_hz,
        "diagnostic_erasure_groups": list(receiver.status.diagnostic_erasure_groups),
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
    parser.add_argument("--station-catalog", type=Path,
                        help="Persist verified and experimental station identities separately")
    parser.add_argument("--persistent-sync", action="store_true",
                        help="Enable persistent synchronization for strict-path comparison")
    parser.add_argument("--extractor-cutoff-hz", type=float, default=3_000.0,
                        help="RDS subcarrier low-pass cutoff (try 2100 for recorded 94.7 IQ)")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not 500 <= args.extractor_cutoff_hz <= 5500:
        parser.error("--extractor-cutoff-hz must be between 500 and 5500")
    catalog = StationCatalog(args.station_catalog) if args.station_catalog else None
    print(json.dumps(replay(args.iq, args.seconds, catalog,
                            persistent_sync=args.persistent_sync,
                            extractor_cutoff_hz=args.extractor_cutoff_hz), indent=2))


if __name__ == "__main__":
    main()
