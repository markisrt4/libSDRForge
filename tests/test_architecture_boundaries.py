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
        PACKAGE / "controllers" / "receiver_manager.py",
        PACKAGE / "simulation" / "fault_injecting_receiver.py",
        PACKAGE / "simulation" / "simulated_receiver.py",
        PACKAGE / "protocols" / "rigctl" / "command_handler.py",
    ]
    for path in paths:
        imports = _imports(path)
        assert not any(
            name == "sdrforge.rigctl_server"
            or name.startswith(("sdrforge.protocols.", "sdrforge.applications."))
            for name in imports
        ), f"{path} depends on transport/application layer"


def test_library_never_imports_openroadcode():
    for path in PACKAGE.rglob("*.py"):
        imports = _imports(path)
        assert not any(
            name in {"OpenRoadCode", "openroadcode"}
            or name.startswith(("OpenRoadCode.", "openroadcode."))
            for name in imports
        ), f"{path} imports OpenRoadCode"


def test_production_core_does_not_depend_on_simulation():
    paths = [
        PACKAGE / "interfaces" / "receiver_control.py",
        PACKAGE / "controllers" / "receiver_manager.py",
        PACKAGE / "adapters" / "rtl_sdr.py",
        PACKAGE / "protocols" / "rigctl" / "server.py",
        PACKAGE / "protocols" / "rigctl" / "command_handler.py",
    ]
    for path in paths:
        assert not any(
            name == "sdrforge.simulation" or name.startswith("sdrforge.simulation.")
            for name in _imports(path)
        ), f"{path} must not depend on simulation"


def test_rigctl_interpreter_has_no_tcp_dependency():
    path = PACKAGE / "protocols" / "rigctl" / "command_handler.py"
    imports = _imports(path)
    assert "socket" not in imports
    assert "socketserver" not in imports
    assert "sdrforge.protocols.rigctl.server" not in imports
