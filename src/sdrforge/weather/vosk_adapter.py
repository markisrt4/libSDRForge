"""!
@brief Optional, fully local Vosk adapter for NOAA audio.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class VoskOfflineRecognizer:
    """!
    @brief Transcribe mono PCM using an installed local Vosk model.
    """

    def __init__(self, model_path: str | Path) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param model_path The model path value.
        """
        path = Path(model_path).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"Vosk model directory not found: {path}")
        try:
            import vosk
        except ImportError as exc:
            raise RuntimeError("Vosk is not installed; install the optional vosk package") from exc
        self._vosk = vosk
        self._model = vosk.Model(str(path))

    def transcribe(self, pcm: np.ndarray, sample_rate: int) -> str:
        """!
        @brief Provide transcribe behavior.
        @param self The current instance.
        @param pcm The pcm value.
        @param sample_rate The sample rate value.
        @return The operation result.
        """
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        samples = np.asarray(pcm, dtype=np.float32)
        if samples.ndim != 1 or not np.all(np.isfinite(samples)):
            raise ValueError("expected finite mono PCM")
        if np.any(np.abs(samples) > 1):
            raise ValueError("PCM must be normalized to [-1, 1]")
        pcm16 = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
        recognizer = self._vosk.KaldiRecognizer(self._model, sample_rate)
        chunks = []
        for offset in range(0, len(pcm16), 8192):
            if recognizer.AcceptWaveform(pcm16[offset:offset + 8192]):
                chunks.append(json.loads(recognizer.Result()).get("text", ""))
        chunks.append(json.loads(recognizer.FinalResult()).get("text", ""))
        return " ".join(text for text in chunks if text).strip()
