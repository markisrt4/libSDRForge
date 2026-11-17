"""Candidate selection prioritizes complete SAME headers over sync fragments."""
from sdrforge.weather.same_afsk import _candidate_score


HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


def test_complete_header_outscores_repeated_sync_words():
    assert _candidate_score(HEADER) > _candidate_score(b"ZCZC" * 10)


def test_complete_header_outscores_printable_garbage():
    assert _candidate_score(HEADER) > _candidate_score(b"X" * 500)


def test_truncated_header_not_considered_complete():
    assert _candidate_score(HEADER[:-1])[0] == 0


def test_corrupted_header_not_considered_complete():
    assert _candidate_score(HEADER.replace(b"RWT", b"R?T"))[0] == 0


def test_repeated_complete_headers_rank_higher():
    assert _candidate_score(HEADER + HEADER) > _candidate_score(HEADER)


def test_end_marker_does_not_outscore_complete_header():
    assert _candidate_score(HEADER) > _candidate_score(b"NNNN" * 30)
