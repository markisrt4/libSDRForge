"""!
@brief Optional offline Vosk C API binding for Android/Termux and Linux.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
from pathlib import Path
from typing import Self

import numpy as np


class VoskNativeAdapter:
    """!
    @brief Offline speech recognizer backed by libvosk's stable C API.
    """

    def __init__(self, model_path: str | Path, library_path: str | Path | None = None) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param model_path The model path value.
        @param library_path The library path value.
        """
        path = Path(model_path).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"Vosk model directory not found: {path}")
        candidate = (
            str(library_path) if library_path is not None
            else os.environ.get("SDRFORGE_VOSK_LIBRARY")
            or ctypes.util.find_library("vosk")
        )
        if not candidate:
            raise RuntimeError(
                "Native Vosk library not found. Provide --vosk-library PATH or "
                "set SDRFORGE_VOSK_LIBRARY to a compatible Android/Linux libvosk.so"
            )
        try:
            lib = ctypes.CDLL(candidate)
        except OSError as exc:
            raise RuntimeError(f"Unable to load native Vosk library {candidate}: {exc}") from exc
        self._configure(lib)
        model = lib.vosk_model_new(os.fsencode(path))
        if not model:
            raise RuntimeError(f"Vosk could not load model: {path}")
        self._lib = lib
        self._model = model

    @staticmethod
    def _configure(lib: ctypes.CDLL) -> None:
        signatures = {
            "vosk_model_new": ([ctypes.c_char_p], ctypes.c_void_p),
            "vosk_model_free": ([ctypes.c_void_p], None),
            "vosk_recognizer_new": ([ctypes.c_void_p, ctypes.c_float], ctypes.c_void_p),
            "vosk_recognizer_free": ([ctypes.c_void_p], None),
            "vosk_recognizer_accept_waveform": (
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int], ctypes.c_int
            ),
            "vosk_recognizer_result": ([ctypes.c_void_p], ctypes.c_char_p),
            "vosk_recognizer_final_result": ([ctypes.c_void_p], ctypes.c_char_p),
        }
        try:
            for name, (args, result) in signatures.items():
                func = getattr(lib, name)
                func.argtypes = args
                func.restype = result
        except AttributeError as exc:
            raise RuntimeError(f"Native Vosk library missing required C API symbol: {exc}") from exc

    def close(self) -> None:
        """!
        @brief Provide close behavior.
        @param self The current instance.
        """
        model = getattr(self, "_model", None)
        if model:
            self._model = None
            self._lib.vosk_model_free(model)

    def __enter__(self) -> Self:
        """!
        @brief Provide   enter   behavior.
        @param self The current instance.
        @return The operation result.
        """
        return self

    def __exit__(self, *_: object) -> None:
        """!
        @brief Provide   exit   behavior.
        @param self The current instance.
        @param _ The   value.
        """
        self.close()

    def transcribe(self, pcm: np.ndarray, sample_rate: int) -> str:
        """!
        @brief Provide transcribe behavior.
        @param self The current instance.
        @param pcm The pcm value.
        @param sample_rate The sample rate value.
        @return The operation result.
        """
        if not getattr(self, "_model", None):
            raise RuntimeError("Vosk model is closed")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        samples = np.asarray(pcm, dtype=np.float32)
        if samples.ndim != 1 or not np.all(np.isfinite(samples)):
            raise ValueError("expected finite mono PCM")
        if np.any(np.abs(samples) > 1):
            raise ValueError("PCM must be normalized to [-1, 1]")
        pcm16 = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
        recognizer = self._lib.vosk_recognizer_new(self._model, float(sample_rate))
        if not recognizer:
            raise RuntimeError("Native Vosk recognizer initialization failed")
        try:
            chunks: list[str] = []
            for offset in range(0, len(pcm16), 8192):
                block = pcm16[offset:offset + 8192]
                buffer = ctypes.create_string_buffer(block)
                accepted = self._lib.vosk_recognizer_accept_waveform(
                    recognizer, ctypes.cast(buffer, ctypes.c_void_p), len(block)
                )
                if accepted < 0:
                    raise RuntimeError("Native Vosk rejected PCM input")
                if accepted:
                    raw = self._lib.vosk_recognizer_result(recognizer)
                    if raw:
                        chunks.append(json.loads(raw.decode("utf-8")).get("text", ""))
            raw = self._lib.vosk_recognizer_final_result(recognizer)
            if raw:
                chunks.append(json.loads(raw.decode("utf-8")).get("text", ""))
            return " ".join(chunk for chunk in chunks if chunk).strip()
        finally:
            self._lib.vosk_recognizer_free(recognizer)
