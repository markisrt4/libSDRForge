"""Raw unsigned 8-bit RTL-SDR IQ replay integration tests."""
import json

import numpy as np
import pytest

from sdrforge.adsb.iq_synthetic import synthesize_iq
from sdrforge.adsb.receiver_cli import SYNTHETIC_FRAMES, main, run_iq_replay


@pytest.mark.parametrize("rate", [2e6, 2.4e6])
@pytest.mark.parametrize("chunk", [17, 256, 16384])
def test_iq_replay_to_aircraft(tmp_path, rate, chunk):
    frames = tuple(bytes.fromhex(x) for x in SYNTHETIC_FRAMES[:2])
    iq = synthesize_iq(frames, rate, noise=.005, seed=3)
    interleaved = np.empty(len(iq) * 2, dtype=np.uint8)
    interleaved[::2] = np.clip(np.rint(iq.real * 100 + 127.5), 0, 255).astype(np.uint8)
    interleaved[1::2] = np.clip(np.rint(iq.imag * 100 + 127.5), 0, 255).astype(np.uint8)
    path = tmp_path / "adsb.cu8"
    path.write_bytes(interleaved.tobytes())
    output = []
    stats = run_iq_replay(path=path, sample_rate=rate, chunk_samples=chunk, emit=output.append)
    assert stats.frames_valid == 2
    assert stats.position_fixes == 1
    assert json.loads(output[-1])["samples_processed"] == len(iq)


def test_replay_cli_requires_file():
    with pytest.raises(SystemExit) as exc:
        main(["--source", "iq-replay"])
    assert exc.value.code == 2


def test_replay_empty_file(tmp_path):
    path = tmp_path / "empty.cu8"
    path.write_bytes(b"")
    output = []
    stats = run_iq_replay(path=path, emit=output.append)
    assert stats.frames_seen == 0
    assert json.loads(output[-1])["samples_processed"] == 0
