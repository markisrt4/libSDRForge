# SPDX-License-Identifier: MIT
"""Migrate legacy ORC user presets while the SDRForge service is stopped."""

import argparse
import os
from pathlib import Path

from sdrforge.adapters.json_preset_store import JsonPresetStore
from sdrforge.adapters.orc_radio_import import (
    import_orc_radio_data,
    persist_imported_user_presets,
)
from sdrforge.adapters.preset_paths import default_preset_path


def main() -> None:
    """Preview migration by default; write only with explicit approval."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radio-root", type=Path, required=True)
    parser.add_argument("--locale", required=True)
    parser.add_argument(
        "--legacy-presets",
        type=Path,
        default=config / "openroadcode" / "radio_presets.json",
    )
    parser.add_argument("--presets-path", type=Path, default=default_preset_path())
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.legacy_presets.is_file():
        print("No legacy user preset file found; nothing to migrate.")
        return
    if args.legacy_presets.resolve() == args.presets_path.resolve():
        parser.error("Source and destination must be different files")
    data = import_orc_radio_data(
        args.radio_root, locale=args.locale, user_presets_path=args.legacy_presets
    )
    store = JsonPresetStore(args.presets_path)
    existing = {preset.id for preset in store.list_presets()}
    pending = [preset for preset in data.user_presets if preset.id not in existing]
    print(f"Legacy presets: {len(data.user_presets)}; new presets: {len(pending)}")
    print(f"Destination: {args.presets_path}")
    if args.apply:
        print(f"Imported: {persist_imported_user_presets(data, store)}")
    else:
        print("Dry run only. Stop SDRForge before running with --apply.")


if __name__ == "__main__":
    main()
