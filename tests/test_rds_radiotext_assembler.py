# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Conservative streaming RadioText assembly regression tests."""
from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.rds_radiotext_assembler import RdsRadioTextAssembler


def segment(index, text, *, pi=0x5BDB, ab=0, corrected=0):
    assert len(text) == 4
    values = text.encode("latin-1")
    return RdsGroup(pi, 0x2000 | (ab << 4) | index,
                    (values[0] << 8) | values[1],
                    (values[2] << 8) | values[3], False,
                    corrected_bits=corrected)


def test_full_message_and_terminator():
    assembler = RdsRadioTextAssembler()
    pieces = ["POIS", "ON -", " Eve", "ry R", "ose ",
              "Has ", "Its ", "Thor", "n  \r"]
    for index, piece in enumerate(pieces):
        result = assembler.process(segment(index, piece, corrected=2))
    assert result is not None
    assert result.preview == "POISON - Every Rose Has Its Thorn  "
    assert result.complete
    assert result.terminator_seen
    assert result.observations == 9
    assert result.corrected_observations == 9


def test_missing_segment_blocks_completion():
    assembler = RdsRadioTextAssembler()
    assembler.process(segment(0, "ABCD"))
    result = assembler.process(segment(2, "EF\r "))
    assert result is not None
    assert not result.complete
    assert result.missing_segments == (1,)


def test_conflicts_do_not_choose_payload():
    assembler = RdsRadioTextAssembler()
    assembler.process(segment(0, "ABCD"))
    result = assembler.process(segment(0, "WXYZ"))
    assert result is not None
    assert result.conflicting_segments == (0,)
    assert result.preview.startswith("????")
    assert not result.complete


def test_ab_toggle_starts_new_epoch():
    assembler = RdsRadioTextAssembler()
    assembler.process(segment(0, "ABCD"))
    result = assembler.process(segment(0, "WXYZ", ab=1))
    assert result is not None
    assert result.preview.startswith("WXYZ")
    assert result.observations == 1


def test_literal_question_mark_not_treated_as_gap():
    assembler = RdsRadioTextAssembler()
    result = assembler.process(segment(0, "WHY?"))
    assert result is not None
    assert result.missing_segments == ()
