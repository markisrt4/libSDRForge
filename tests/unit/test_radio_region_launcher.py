# SPDX-License-Identifier: MIT
"""Persistent radio-region launcher environment behavior."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
LOADER = ROOT / "scripts" / "run_radio_region_server.sh"


def _load(tmp_path, content, *, override=None):
    config = tmp_path / "radio-region.conf"
    config.write_text(content, encoding="utf-8")
    env = dict(os.environ, SDRFORGE_REGION_CONFIG=str(config))
    env.pop("SDRFORGE_RADIO_ROOT", None)
    env.pop("SDRFORGE_RADIO_LOCALE", None)
    if override:
        env.update(override)
    result = subprocess.run(
        ["bash", str(LOADER), "python", "-c",
         "import os; print(os.environ.get('SDRFORGE_RADIO_ROOT', '')); "
         "print(os.environ.get('SDRFORGE_RADIO_LOCALE', ''))"],
        capture_output=True, text=True, check=True, env=env,
    )
    return result.stdout.splitlines()


def test_persistent_region_loaded(tmp_path):
    assert _load(tmp_path, "SDRFORGE_RADIO_ROOT=/some/path\nSDRFORGE_RADIO_LOCALE=romeo\n") == [
        "/some/path", "romeo",
    ]


def test_explicit_environment_takes_precedence(tmp_path):
    assert _load(tmp_path, "SDRFORGE_RADIO_ROOT=/stored\nSDRFORGE_RADIO_LOCALE=romeo\n",
                 override={"SDRFORGE_RADIO_LOCALE": "other"}) == ["/stored", "other"]


def test_config_is_not_executed(tmp_path):
    marker = tmp_path / "injected"
    assert _load(tmp_path, f"UNKNOWN=$(touch {marker})\n") == ["", ""]
    assert not marker.exists()
