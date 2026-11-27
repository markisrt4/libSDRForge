"""Repeated SAME voting never constitutes alert confirmation."""

import numpy as np
import pytest

from sdrforge.weather.same_benchmark import HEADER
from sdrforge.weather.same_combine import combine_same_bursts
from sdrforge.weather.same_messages import confirm_same_messages


def test_three_corrupted_copies_recover_complete_header():
    bursts = []
    for index in (3, 10, 20):
        changed = bytearray(HEADER)
        changed[index] ^= 1
        bursts.append(bytes(changed))
    combined = combine_same_bursts(bursts)
    assert combined.candidate == HEADER
    assert combined.complete_header
    assert not combined.verified


def test_reconstructed_header_is_not_confirmed_alert():
    bursts = []
    for index in (3, 10, 20):
        changed = bytearray(HEADER)
        changed[index] ^= 1
        bursts.append(bytes(changed))
    result = combine_same_bursts(bursts)
    assert not confirm_same_messages(result.candidate).alerts


def test_weighted_vote_can_override_unweighted_majority():
    bursts = [b"\x01", b"\x00", b"\x00"]
    weights = (np.array([10.0] + [1.0] * 7), np.ones(8), np.ones(8))
    assert combine_same_bursts(bursts).candidate == b"\x00"
    assert combine_same_bursts(bursts, confidences=weights).candidate == b"\x01"


def test_rejects_unaligned_bursts():
    with pytest.raises(ValueError):
        combine_same_bursts([b"ABC", b"AB", b"ABC"])


def test_rejects_insufficient_repetitions():
    with pytest.raises(ValueError):
        combine_same_bursts([HEADER, HEADER])


def test_rejects_bad_weights():
    with pytest.raises(ValueError):
        combine_same_bursts(
            [b"A"] * 3, confidences=(np.ones(8), np.ones(8), np.full(8, np.nan))
        )


def test_corrupt_repetitions_not_complete():
    result = combine_same_bursts([b"garbage"] * 3)
    assert not result.complete_header
    assert not result.verified
