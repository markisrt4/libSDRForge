# SPDX-License-Identifier: MIT
"""Managed acquisition authorization regression tests."""

from threading import Event
from unittest.mock import Mock

import pytest

from sdrforge.controllers.receiver_manager import ReceiverManager


@pytest.mark.parametrize("method", ["start", "start_async"])
@pytest.mark.parametrize("token", [None, "incorrect"])
def test_unauthorized_start(method: str, token: str | None) -> None:
    receiver = Mock()
    manager = ReceiverManager(receiver, acquisition_token="test-token")
    with pytest.raises(PermissionError, match="authorization"):
        getattr(manager, method)(token=token)
    receiver.start.assert_not_called()
    assert not manager.running
    assert not manager.starting


def test_authorized_start() -> None:
    receiver = Mock()
    manager = ReceiverManager(receiver, acquisition_token="test-token")
    manager.start(token="test-token")
    receiver.start.assert_called_once_with()
    assert manager.running
    manager.stop(token="test-token")
    receiver.stop.assert_called_once_with()


def test_standalone_start() -> None:
    receiver = Mock()
    manager = ReceiverManager(receiver)
    manager.start()
    receiver.start.assert_called_once_with()


def test_empty_credential_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        ReceiverManager(Mock(), acquisition_token="")


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("stop", ()),
        ("set_frequency", (94_700_000,)),
        ("set_mode", ("WFM", 200_000)),
        ("pan_acquisition", (94_700_000,)),
        ("recenter", ()),
        ("set_rf_configuration", ({"device_serial": "001"},)),
    ],
)
def test_managed_mutations_require_credential(method: str, args: tuple) -> None:
    receiver = Mock()
    manager = ReceiverManager(receiver, acquisition_token="test-token")
    if method == "stop":
        manager.start(token="test-token")
    mutate = getattr(manager, method)
    with pytest.raises(PermissionError, match="authorization"):
        mutate(*args)
    backend = getattr(receiver, method)
    backend.assert_not_called()
    mutate(*args, token="test-token")
    backend.assert_called_once_with(*args)


def test_deferred_stop_does_not_report_early_release() -> None:
    receiver = Mock()
    started = Event()
    unblock = Event()

    def start() -> None:
        started.set()
        assert unblock.wait(timeout=2)

    receiver.start.side_effect = start
    receiver.get_release_status.return_value = {"hardware_released": True}
    manager = ReceiverManager(receiver, acquisition_token="test-token")
    manager.start_async(token="test-token")
    try:
        assert started.wait(timeout=2)
        manager.stop(token="test-token")
        assert manager.get_release_status()["hardware_released"] is False
        receiver.stop.assert_not_called()
    finally:
        unblock.set()
        manager.close()
    receiver.stop.assert_called_once_with()
    assert manager.get_release_status()["hardware_released"] is True


def test_failed_async_start_cleans_up_during_process_close() -> None:
    receiver = Mock()
    receiver.start.side_effect = RuntimeError("USB disconnected")
    receiver.get_release_status.return_value = {"hardware_released": True}
    manager = ReceiverManager(receiver, acquisition_token="test-token")
    manager.start_async(token="test-token")
    manager.close()
    assert manager.startup_error == "USB disconnected"
    receiver.stop.assert_called_once_with()
    assert not manager.running
