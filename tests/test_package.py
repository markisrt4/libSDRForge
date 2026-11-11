"""Hardware-free packaging smoke tests."""

import sdrforge


def test_package_version() -> None:
    assert sdrforge.__version__ == "0.1.0"
