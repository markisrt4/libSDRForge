"""SAME noise benchmark contracts, not fabricated reception guarantees."""
import numpy as np
import pytest

from sdrforge.weather.same_benchmark import add_awgn, benchmark


def test_awgn_is_reproducible():
    signal = np.ones(1000)
    a = add_awgn(signal, 10, np.random.default_rng(42))
    b = add_awgn(signal, 10, np.random.default_rng(42))
    np.testing.assert_array_equal(a, b)


def test_awgn_zero_signal_unchanged():
    np.testing.assert_array_equal(
        add_awgn(np.zeros(100), 0, np.random.default_rng(1)),
        np.zeros(100))


def test_awgn_noise_power_near_target():
    signal = np.ones(100000)
    noisy = add_awgn(signal, 10, np.random.default_rng(2))
    assert 0.08 < np.mean((noisy - signal) ** 2) < 0.12


def test_nominal_clean_header_recovers():
    rows = benchmark(snrs=(80.0,), baud_errors=(0.0,), trials=1)
    assert rows[0].exact_headers == 1
    assert rows[0].success_rate == 1.0


def test_benchmark_repeatable():
    kwargs = dict(snrs=(15.0,), baud_errors=(0.0,), trials=1, seed=19)
    assert benchmark(**kwargs) == benchmark(**kwargs)


def test_unknown_clock_mode_reports_mode():
    rows = benchmark(snrs=(80.0,), baud_errors=(0.0,), trials=1,
                     known_clock=False)
    assert rows[0].known_clock is False
    assert 0 <= rows[0].exact_headers <= 1


@pytest.mark.parametrize("trials", [0, -1])
def test_invalid_trials(trials):
    with pytest.raises(ValueError):
        benchmark(trials=trials)


def test_invalid_snr():
    with pytest.raises(ValueError):
        benchmark(snrs=(float("nan"),))


def test_invalid_baud_error():
    with pytest.raises(ValueError):
        benchmark(baud_errors=(-1000.0,))
