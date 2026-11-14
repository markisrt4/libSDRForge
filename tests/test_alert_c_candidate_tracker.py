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
    assert report["candidates"][0]["status"] == "incomplete_unverified"


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
