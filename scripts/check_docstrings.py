#!/usr/bin/env python3
"""Enforce documentation coverage for the non-private Python API."""

from __future__ import annotations

import ast
from pathlib import Path


SOURCE_ROOT = Path("src/sdrforge")


def _public_symbols(path: Path) -> list[tuple[int, str, ast.AST]]:
    """Return public modules, classes, functions, and methods in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols: list[tuple[int, str, ast.AST]] = [(1, "module", tree)]

    def visit(body: list[ast.stmt], owner: str | None = None) -> None:
        """Collect public definitions without descending into local functions."""
        for node in body:
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                qualified_name = f"{owner}.{node.name}" if owner else node.name
                symbols.append((node.lineno, qualified_name, node))
                visit(node.body, qualified_name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                qualified_name = f"{owner}.{node.name}" if owner else node.name
                symbols.append((node.lineno, qualified_name, node))

    visit(tree.body)
    return symbols


def undocumented_symbols(root: Path = SOURCE_ROOT) -> list[str]:
    """Return source locations for non-private symbols lacking docstrings."""
    missing: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for line, name, node in _public_symbols(path):
            if ast.get_docstring(node, clean=False) is None:
                missing.append(f"{path}:{line}: {name}")
    return missing


def main() -> int:
    """Print missing documentation and return a CI-friendly status code."""
    missing = undocumented_symbols()
    if not missing:
        print("All non-private Python modules, classes, functions, and methods are documented.")
        return 0

    print("Missing docstrings:")
    for location in missing:
        print(f"  {location}")
    print(f"\n{len(missing)} non-private symbol(s) require documentation.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
