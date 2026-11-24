# SPDX-License-Identifier: MIT
"""!
@brief Platform-independent, writable location for SDRForge preset storage.
"""
from __future__ import annotations

import os
from pathlib import Path


def default_preset_path() -> Path:
    """!
    @brief Resolve the JSON store using an explicit override or XDG conventions.
    @return Writable preset store path.
    """
    override = os.environ.get("SDRFORGE_PRESETS_PATH")
    if override:
        return Path(override).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return root / "sdrforge" / "radio_presets.json"
