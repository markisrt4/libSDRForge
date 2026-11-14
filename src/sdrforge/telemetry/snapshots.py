# SPDX-License-Identifier: MIT
"""Build JSON-safe receiver snapshots without coupling DSP to networking."""
from __future__ import annotations

import math
import time
from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np


def _json_value(value: Any) -> Any:
    """Convert common DSP and metadata values to strict JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    raise TypeError(f"unsupported telemetry type: {type(value).__name__}")


def spectrum_snapshot(
    power_db: np.ndarray,
    *,
    center_frequency_hz: int,
    sample_rate_hz: int,
    timestamp_ns: int | None = None,
) -> dict[str, Any]:
    """Describe ordered FFT bins spanning the given sample rate.

    power_db must already be fftshift-ordered and converted to dB by the
    upstream spectrum analyzer. No FFT work is performed here.
    """
    bins = np.asarray(power_db)
    if bins.ndim != 1 or bins.size == 0:
        raise ValueError("spectrum requires a nonempty one-dimensional array")
    if not np.issubdtype(bins.dtype, np.number):
        raise TypeError("spectrum bins must be numeric")
    if sample_rate_hz <= 0 or center_frequency_hz <= 0:
        raise ValueError("sample rate and center frequency must be positive")
    return {
        "timestamp_ns": time.time_ns() if timestamp_ns is None else timestamp_ns,
        "center_frequency_hz": center_frequency_hz,
        "sample_rate_hz": sample_rate_hz,
        "bin_count": int(bins.size),
        "first_bin_frequency_hz": center_frequency_hz - sample_rate_hz / 2,
        "bin_spacing_hz": sample_rate_hz / int(bins.size),
        "power_db": _json_value(bins),
    }


def receiver_snapshot(receiver: Any, *, timestamp_ns: int | None = None) -> dict[str, Any]:
    """Read the current WBFM metadata without requiring any hardware access."""
    report = _json_value(receiver.tmc_candidate_report)
    if report is not None:
        # Candidates remain diagnostics, not traffic alerts.
        report["usable_for_navigation"] = False
    return {
        "timestamp_ns": time.time_ns() if timestamp_ns is None else timestamp_ns,
        "channel_frequency_hz": receiver.channel_frequency_hz,
        "stereo_locked": receiver.stereo_locked,
        "stereo_blend": receiver.stereo_blend,
        "rds": _json_value(receiver.rds_status),
        "rds_group_count": len(receiver.last_rds_groups),
        "tmc_diagnostics": report,
    }
