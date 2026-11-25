# SPDX-License-Identifier: MIT
"""Managed acquisition authorization regression tests."""

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
    manager.stop()
    receiver.stop.assert_called_once_with()


def test_standalone_start() -> None:
    receiver = Mock()
    manager = ReceiverManager(receiver)
    manager.start()
    receiver.start.assert_called_once_with()


def test_empty_credential_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        ReceiverManager(Mock(), acquisition_token="")
