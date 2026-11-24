"""Unit tests for native Vosk adapter input validation without a native library."""

from __future__ import annotations

import numpy as np
import pytest

from sdrforge.weather.vosk_native import VoskNativeAdapter


def test_missing_model_rejected(tmp_path):
    with pytest.raises(FileNotFoundError, match="Vosk model directory"):
        VoskNativeAdapter(tmp_path / "missing", "/does/not/exist/libvosk.so")


def test_missing_native_library_rejected(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    with pytest.raises(RuntimeError, match="Unable to load native Vosk library"):
        VoskNativeAdapter(model, "/does/not/exist/libvosk.so")


def test_validation_before_native_recognizer():
    adapter = object.__new__(VoskNativeAdapter)
    adapter._model = 1
    for audio, rate in [
        (np.array([float("nan")]), 16000),
        (np.array([[0.0]]), 16000),
        (np.array([1.5]), 16000),
        (np.array([0.0]), 0),
    ]:
        with pytest.raises(ValueError):
            adapter.transcribe(audio, rate)
