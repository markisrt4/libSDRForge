# SPDX-License-Identifier: MIT
"""Public import compatibility during package reorganization."""
from sdrforge.controllers.receiver_manager import ReceiverManager as CanonicalManager
from sdrforge.receiver_manager import ReceiverManager
from sdrforge.adapters.fault_injecting_receiver import (
    FaultInjectingReceiver as CanonicalFaultInjector,
)
from sdrforge.fault_injecting_receiver import FaultInjectingReceiver
from sdrforge.rigctl_simulator import SimulatedReceiver


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
