# SPDX-License-Identifier: MIT
"""Command-level RigCTL tests, without TCP or SDR hardware."""
import pytest

from sdrforge.rigctl_command_handler import RigctlCommandHandler
from sdrforge.rigctl_simulator import SimulatedReceiver


def test_command_handler_tuning_and_mode():
    handler = RigctlCommandHandler(SimulatedReceiver())
    assert handler.dispatch("f") == "104300000"
    assert handler.dispatch("F 101700000") == "RPRT 0"
    assert handler.dispatch("f") == "101700000"
    assert handler.dispatch("M FM 12000") == "RPRT 0"
    assert handler.dispatch("m") == "FM\n12000"


def test_command_handler_unknown_commands():
    handler = RigctlCommandHandler(SimulatedReceiver())
    assert handler.dispatch("not_a_command") == "RPRT -4"
    assert handler.dispatch("l UNKNOWN") == "RPRT -4"


def test_command_handler_rejects_invalid_parameters():
    handler = RigctlCommandHandler(SimulatedReceiver())
    with pytest.raises(ValueError):
        handler.dispatch("F -1")
    with pytest.raises(ValueError):
        handler.dispatch("M BAD 12000")
