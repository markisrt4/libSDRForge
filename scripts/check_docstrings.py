"""Enforce documentation coverage for the non-private Python API."""

from __future__ import annotations

import ast
import re
from pathlib import Path

SOURCE_ROOT = Path("src/sdrforge")


def _is_documented_name(name: str) -> bool:
    """Return whether a name is public or a public Python special method."""
    return not name.startswith("_") or name.startswith("__") and name.endswith("__")


def _base_name(node: ast.expr) -> str | None:
    """Return the terminal name of a class base expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_interface(node: ast.ClassDef) -> bool:
    """Return whether a class declares a protocol or abstract interface."""
    if any(_base_name(base) in {"Protocol", "ABC"} for base in node.bases):
        return True
    return any(
        isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            _base_name(decorator) == "abstractmethod"
            for decorator in member.decorator_list
        )
        for member in node.body
    )


def _public_symbols(path: Path) -> list[tuple[int, str, ast.AST]]:
    """Return public symbols plus private interface declarations in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols: list[tuple[int, str, ast.AST]] = [(1, "module", tree)]

    def visit(
        body: list[ast.stmt], owner: str | None = None, *, interface: bool = False
    ) -> None:
        """Collect public definitions without descending into local functions."""
        for node in body:
            if isinstance(node, ast.ClassDef):
                node_is_interface = _is_interface(node)
                if node.name.startswith("_") and not node_is_interface:
                    continue
                qualified_name = f"{owner}.{node.name}" if owner else node.name
                symbols.append((node.lineno, qualified_name, node))
                visit(node.body, qualified_name, interface=node_is_interface)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not interface and not _is_documented_name(node.name):
                    continue
                qualified_name = f"{owner}.{node.name}" if owner else node.name
                symbols.append((node.lineno, qualified_name, node))

    visit(tree.body)
    return symbols


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return every declared parameter name for a function or method."""
    args = node.args
    names = [
        argument.arg for argument in (*args.posonlyargs, *args.args, *args.kwonlyargs)
    ]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return names


def _returns_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return whether a function annotation declares a result."""
    annotation = node.returns
    return not (
        annotation is None
        or isinstance(annotation, ast.Constant)
        and annotation.value is None
        or isinstance(annotation, ast.Name)
        and annotation.id == "None"
    )


def documentation_errors(root: Path = SOURCE_ROOT) -> list[str]:
    """Return source locations for incomplete Doxygen documentation."""
    errors: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for line, name, node in _public_symbols(path):
            docstring = ast.get_docstring(node, clean=False)
            location = f"{path}:{line}: {name}"
            if docstring is None:
                errors.append(f"{location}: missing docstring")
                continue
            if not docstring.lstrip().startswith("!"):
                errors.append(f'{location}: Doxygen docstring must start with """!')
            if "@brief" not in docstring:
                errors.append(f"{location}: missing @brief")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for parameter in _parameters(node):
                    pattern = rf"@param(?:\[[^]]+\])?\s+{re.escape(parameter)}\b"
                    if re.search(pattern, docstring) is None:
                        errors.append(f"{location}: missing @param {parameter}")
                if _returns_value(node) and "@return" not in docstring:
                    errors.append(f"{location}: missing @return")
                if not _returns_value(node) and "@return" in docstring:
                    errors.append(f"{location}: unexpected @return for a None return")
    return errors


def main() -> int:
    """Print missing documentation and return a CI-friendly status code."""
    errors = documentation_errors()
    if not errors:
        print("All non-private Python symbols have complete Doxygen documentation.")
        return 0

    print("Doxygen documentation errors:")
    for error in errors:
        print(f"  {error}")
    print(f"\n{len(errors)} documentation error(s) found.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
