#!/usr/bin/env python3
"""Remove sanitize_log_value() from logger args that use numeric format specifiers (%d, %f, etc.)."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"venv", ".venv", "__pycache__", "node_modules", "e2e", "dist", "sandbox-just-test"}

LOG_METHODS = frozenset({"debug", "info", "warning", "error", "critical", "exception", "log"})
LOGGER_NAMES = frozenset({"logger", "structured_logger", "slog"})
NUMERIC_SPEC = re.compile(r"%[-+#0 ]*\d*(?:\.\d+)?[diufFeEgGc]")


def _is_logger_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in LOG_METHODS:
        return False
    value = node.func.value
    if isinstance(value, ast.Name) and value.id in LOGGER_NAMES:
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "getLogger"
    )


def _unwrap_sanitize(source: str, node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name) and node.func.id == "sanitize_log_value":
        seg = ast.get_source_segment(source, node.args[0])
        return seg.strip() if seg else None
    return None


def _format_specs(fmt: str) -> list[str]:
    specs: list[str] = []
    i = 0
    while i < len(fmt):
        if fmt[i] == "%" and i + 1 < len(fmt):
            if fmt[i + 1] == "%":
                i += 2
                continue
            m = NUMERIC_SPEC.match(fmt, i)
            if m:
                specs.append(m.group(0))
                i = m.end()
                continue
            j = i + 1
            while j < len(fmt) and fmt[j] in "-+#0 ":
                j += 1
            while j < len(fmt) and fmt[j].isdigit():
                j += 1
            if j < len(fmt) and fmt[j] == ".":
                j += 1
                while j < len(fmt) and fmt[j].isdigit():
                    j += 1
            if j < len(fmt):
                specs.append(fmt[i : j + 1])
                i = j + 1
                continue
        i += 1
    return specs


def _is_numeric_spec(spec: str) -> bool:
    return spec[-1] in "diufFeEgGc"


def _process_file(path: Path) -> bool:
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    replacements: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_logger_call(node):
            continue
        if not node.args:
            continue
        fmt_node = node.args[0]
        if not isinstance(fmt_node, ast.Constant) or not isinstance(fmt_node.value, str):
            continue
        specs = _format_specs(fmt_node.value)
        if len(specs) != len(node.args) - 1:
            continue
        for idx, (spec, arg) in enumerate(zip(specs, node.args[1:]), start=1):
            if not _is_numeric_spec(spec):
                continue
            inner = _unwrap_sanitize(source, arg)
            if inner is None:
                continue
            arg_src = ast.get_source_segment(source, arg)
            if arg_src:
                replacements.append((arg.lineno, arg.col_offset, arg_src, inner))

    if not replacements:
        return False

    lines = source.splitlines(keepends=True)
    # Apply from bottom of file to preserve offsets (line-based replace)
    by_line: dict[int, list[tuple[str, str]]] = {}
    for lineno, _col, old, new in replacements:
        by_line.setdefault(lineno, []).append((old, new))

    changed = False
    for lineno, pairs in sorted(by_line.items(), reverse=True):
        line = lines[lineno - 1]
        for old, new in pairs:
            if old in line:
                line = line.replace(old, new, 1)
                changed = True
        lines[lineno - 1] = line

    if changed:
        path.write_text("".join(lines))
    return changed


def main() -> int:
    count = 0
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP for part in path.parts):
            continue
        if _process_file(path):
            print(path.relative_to(ROOT))
            count += 1
    print(f"Updated {count} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
