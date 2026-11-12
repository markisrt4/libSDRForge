# SPDX-License-Identifier: MIT
"""Public import compatibility during package reorganization."""
from sdrforge.controllers.receiver_manager import ReceiverManager as CanonicalManager
from sdrforge.receiver_manager import ReceiverManager
from sdrforge.adapters.fault_injecting_receiver import (
    FaultInjectingReceiver as CanonicalFaultInjector,
)
from sdrforge.fault_injecting_receiver import FaultInjectingReceiver
from sdrforge.rigctl_simulator import SimulatedReceiver
from sdrforge.simulation.simulated_receiver import SimulatedReceiver as CanonicalSimulator
from sdrforge.simulation.fault_injecting_receiver import FaultInjectingReceiver as SimulationFaultInjector


def test_receiver_manager_legacy_import_is_canonical_class():
    assert ReceiverManager is CanonicalManager
    manager = ReceiverManager(SimulatedReceiver())
    manager.start()
    assert manager.running


def test_fault_injector_legacy_import_is_canonical_class():
    assert FaultInjectingReceiver is CanonicalFaultInjector
    adapter = FaultInjectingReceiver(SimulatedReceiver())
    adapter.disconnect()
    try:
        adapter.start()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected disconnected receiver to fail")


def test_simulation_imports_are_canonical():
    assert SimulatedReceiver is CanonicalSimulator
    assert FaultInjectingReceiver is SimulationFaultInjector


def test_rigctl_legacy_imports_are_canonical():
    from sdrforge.rigctl_server import RigctlServer, RigctlHandler
    from sdrforge.rigctl_command_handler import RigctlCommandHandler
    from sdrforge.protocols.rigctl.server import RigctlServer as CanonicalServer
    from sdrforge.protocols.rigctl.server import RigctlHandler as CanonicalHandler
    from sdrforge.protocols.rigctl.command_handler import RigctlCommandHandler as CanonicalCommands

    assert RigctlServer is CanonicalServer
    assert RigctlHandler is CanonicalHandler
    assert RigctlCommandHandler is CanonicalCommands
