# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Conservative ALERT-C candidate tracking tests."""
from sdrforge.protocols.rds.alert_c_8a import parse_alert_c_8a
from sdrforge.protocols.rds.alert_c_candidate_tracker import AlertCCandidateTracker
from sdrforge.protocols.rds.rds_block_sync import RdsGroup


def parse(raw: str):
    a, b, c, d = (int(word, 16) for word in raw.split())
    result = parse_alert_c_8a(RdsGroup(a, b, c, d, False,
                                       synchronization="redsea_fec_unknown"))
    assert result is not None
    return result


def test_repetitions_do_not_create_fake_complete_message():
    tracker = AlertCCandidateTracker()
    first = parse("7ADA 80E2 C323 7837")
    continuation = parse("7ADA 80E2 40ED 4400")
    for item in (first, first, first, continuation):
        tracker.process(item)
    report = tracker.summary()
    assert report["candidate_count"] == 1
    assert report["complete_verified"] == 0
    assert report["candidates"][0]["first_repetitions"] == 2
    assert report["candidates"][0]["status"] == "structurally_complete_unverified"
    assert report["candidates"][0]["expected_groups"] == 2


def test_conflicting_first_creates_ambiguous_superseded_candidate():
    tracker = AlertCCandidateTracker()
    tracker.process(parse("7ADA 80E1 8846 0DFC"))
    tracker.process(parse("7ADA 80E1 C323 7837"))
    report = tracker.summary()
    assert report["candidate_count"] == 2
    assert report["candidates"][0]["ambiguous"] is True
    assert report["candidates"][0]["status"] == "superseded_unverified"


def test_orphan_continuation_is_not_a_traffic_event():
    tracker = AlertCCandidateTracker()
    tracker.process(parse("7ADA 80E3 0440 0000"))
    report = tracker.summary()
    assert report["orphan_continuations"] == 1
    assert report["complete_verified"] == 0
    assert report["candidates"][0]["first_event_code_raw"] is None

def test_sequence_countdown_three_group_message():
    tracker = AlertCCandidateTracker()
    for raw in (
        "7ADA 80E3 C2BE 0DFC",
        "7ADA 80E3 5733 F0ED",
        "7ADA 80E3 0440 0000",
    ):
        tracker.process(parse(raw))
    report = tracker.summary()
    assert report["structurally_complete_unverified"] == 1
    assert report["complete_verified"] == 0
    assert report["candidates"][0]["expected_groups"] == 3


def test_out_of_order_countdown_is_not_complete():
    tracker = AlertCCandidateTracker()
    for raw in (
        "7ADA 80E3 C2BE 0DFC",
        "7ADA 80E3 0440 0000",
        "7ADA 80E3 5733 F0ED",
    ):
        tracker.process(parse(raw))
    assert tracker.summary()["candidates"][0]["status"] == "sequence_conflict_unverified"

def test_repetition_confidence_is_not_reception_verification():
    tracker = AlertCCandidateTracker()
    first = parse("7ADA 80E1 8846 0DFC")
    last = parse("7ADA 80E1 42A1 2000")
    for item in (first, first, last, last):
        tracker.process(item)
    candidate = tracker.summary()["candidates"][0]
    assert candidate["structurally_complete"]
    assert candidate["first_observations"] == 2
    assert candidate["continuation_observations"] == [2]
    assert candidate["repetition_confidence"] == "repeated_all_groups"
    assert candidate["reception_verified"] is False
    assert candidate["usable_for_navigation"] is False
    assert candidate["next_sequence"] is None


def test_partial_repetition_and_unresolved_location():
    tracker = AlertCCandidateTracker()
    for raw in (
        "7ADA 80E3 C2BE 0DFC",
        "7ADA 80E3 5733 F0ED",
        "7ADA 80E3 5733 F0ED",
        "7ADA 80E3 0440 0000",
    ):
        tracker.process(parse(raw))
    candidate = tracker.summary()["candidates"][0]
    assert candidate["repetition_confidence"] == "partial_repetition"
    assert candidate["continuation_observations"] == [2, 1]
    assert candidate["location_resolution"] == "unresolved"
    assert candidate["traffic_event_verified"] is False

def test_candidate_history_is_bounded_and_eviction_removes_active():
    tracker = AlertCCandidateTracker(max_candidates=2)
    tracker.process(parse("7ADA 80E1 8846 0DFC"))
    tracker.process(parse("7ADA 80E2 C323 7837"))
    tracker.process(parse("7ADA 80E3 C2BE 0DFC"))
    assert [item.continuity_index for item in tracker.candidates] == [2, 3]
    tracker.process(parse("7ADA 80E1 42A1 2000"))
    assert tracker.orphan_continuations == 1
    assert len(tracker.candidates) == 2


def test_candidate_limit_validation():
    import pytest

    with pytest.raises(ValueError):
        AlertCCandidateTracker(max_candidates=0)
