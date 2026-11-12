# SPDX-License-Identifier: MIT
"""Guard architectural dependency direction without requiring hardware."""
import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "sdrforge"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_receiver_core_does_not_import_protocol_or_application_layers():
    paths = [
        PACKAGE / "interfaces" / "receiver_control.py",
        PACKAGE / "receiver_manager.py",
        PACKAGE / "fault_injecting_receiver.py",
        PACKAGE / "rigctl_command_handler.py",
    ]
    for path in paths:
        imports = _imports(path)
        assert not any(
            name == "sdrforge.rigctl_server"
            or name.startswith("sdrforge.protocols.")
            or name.startswith("sdrforge.applications.")
            for name in imports
        ), f"{path} depends on transport/application layer"


def test_library_never_imports_openroadcode():
    for path in PACKAGE.rglob("*.py"):
        imports = _imports(path)
        assert not any(
            name == "OpenRoadCode"
            or name.startswith("OpenRoadCode.")
            or name == "openroadcode"
            or name.startswith("openroadcode.")
            for name in imports
        ), f"{path} imports OpenRoadCode"
