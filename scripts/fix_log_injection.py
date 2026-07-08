#!/usr/bin/env python3
"""Convert logger f-strings to %s style with sanitize_log_value() for CodeQL log-injection."""

from __future__ import annotations

import ast
import os
import re
import sys
from typing import Iterable, List, Optional, Tuple

LOG_METHODS = frozenset(
    {"debug", "info", "warning", "error", "critical", "exception", "log"}
)
LOGGER_NAMES = frozenset({"logger", "structured_logger", "slog"})
SAFE_WRAP_FUNCS = frozenset(
    {
        "sanitize_log_value",
        "mask_email",
        "redact_sensitive_data",
        "_mask_email",
        "_log_user_email",
    }
)
SKIP_DIRS = {
    "venv",
    ".venv",
    "__pycache__",
    ".git",
    "node_modules",
    "e2e",
    "dist",
    "sandbox-just-test",
}


def _is_logger_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in LOG_METHODS:
        return False
    value = node.func.value
    if isinstance(value, ast.Name) and value.id in LOGGER_NAMES:
        return True
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "getLogger"
    ):
        return True
    return False


def _expr_source(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    if segment is None:
        raise ValueError(f"Could not get source for {ast.dump(node)}")
    return segment.strip()


def _needs_sanitize(expr_src: str) -> bool:
    stripped = expr_src.strip()
    for func in SAFE_WRAP_FUNCS:
        if stripped.startswith(f"{func}("):
            return False
    return True


def _wrap_expr(expr_src: str) -> str:
    if not _needs_sanitize(expr_src):
        return expr_src
    return f"sanitize_log_value({expr_src})"


def _convert_joined_str(source: str, joined: ast.JoinedStr) -> Tuple[str, List[str]]:
    parts: List[str] = []
    args: List[str] = []
    for value in joined.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value.replace("%", "%%"))
        elif isinstance(value, ast.FormattedValue):
            parts.append("%s")
            args.append(_wrap_expr(_expr_source(source, value.value)))
        else:
            raise ValueError(f"Unexpected JoinedStr part: {ast.dump(value)}")
    return "".join(parts), args


def _convert_fstring_call(source: str, node: ast.Call) -> str:
    first = node.args[0]
    if not isinstance(first, ast.JoinedStr):
        raise ValueError("Expected JoinedStr first arg")

    msg, dynamic_args = _convert_joined_str(source, first)
    new_args = [repr(msg)] + dynamic_args + [
        _expr_source(source, arg) for arg in node.args[1:]
    ]

    func_src = _expr_source(source, node.func)
    kw_parts = []
    for kw in node.keywords:
        if kw.arg is None:
            kw_parts.append(f"**{_expr_source(source, kw.value)}")
        else:
            kw_parts.append(f"{kw.arg}={_expr_source(source, kw.value)}")

    all_args = new_args + kw_parts
    return f"{func_src}({', '.join(all_args)})"


def _convert_percent_call(source: str, node: ast.Call) -> Optional[str]:
    if not node.args or len(node.args) < 2:
        return None
    if isinstance(node.args[0], ast.JoinedStr):
        return None
    first_arg = node.args[0]
    if not (
        isinstance(first_arg, ast.Constant)
        and isinstance(first_arg.value, str)
        and "%" in first_arg.value
    ):
        return None
    fmt = first_arg.value
    placeholder_count = fmt.count("%s") + fmt.count("%d") + fmt.count("%r")
    if placeholder_count == 0:
        return None
    dynamic = node.args[1 : 1 + placeholder_count]
    if len(dynamic) != placeholder_count:
        return None
    new_arg_srcs: List[str] = []
    changed = False
    for arg in dynamic:
        src = _expr_source(source, arg)
        if _needs_sanitize(src):
            new_arg_srcs.append(_wrap_expr(src))
            changed = True
        else:
            new_arg_srcs.append(src)
    if not changed:
        return None
    func_src = _expr_source(source, node.func)
    all_args = [repr(fmt)] + new_arg_srcs
    for extra in node.args[1 + placeholder_count :]:
        all_args.append(_expr_source(source, extra))
    for kw in node.keywords:
        if kw.arg is None:
            all_args.append(f"**{_expr_source(source, kw.value)}")
        else:
            all_args.append(f"{kw.arg}={_expr_source(source, kw.value)}")
    return f"{func_src}({', '.join(all_args)})"


def _ensure_import(source: str) -> str:
    if re.search(
        r"from utils\.logging_config import[^\n]*\bsanitize_log_value\b", source
    ):
        return source
    import_line = "from utils.logging_config import sanitize_log_value\n"
    lines = source.splitlines(keepends=True)
    insert_at = 0
    in_parens = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_at = i + 1
            in_parens = "(" in line and ")" not in line
        elif in_parens:
            insert_at = i + 1
            if ")" in line:
                in_parens = False
        elif line.strip() and not line.startswith("#") and insert_at > 0 and not in_parens:
            break
    if insert_at == 0:
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith("#"):
                insert_at = i
                break
    lines.insert(insert_at, import_line)
    return "".join(lines)


def fix_file(path: str, dry_run: bool = False) -> bool:
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    original = source
    tree = ast.parse(source)
    replacements: List[Tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_logger_call(node):
            continue
        if not node.args:
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        old = ast.get_source_segment(source, node)
        if old is None:
            continue
        try:
            if isinstance(node.args[0], ast.JoinedStr):
                new_call = _convert_fstring_call(source, node)
            else:
                new_call = _convert_percent_call(source, node)
                if new_call is None:
                    continue
        except ValueError:
            continue
        if new_call is None or new_call == old.strip():
            continue
        replacements.append((start, end, new_call))

    if not replacements:
        return False

    lines = source.splitlines(keepends=True)
    for start, end, new_call in sorted(replacements, key=lambda x: x[0], reverse=True):
        indent = re.match(r"^(\s*)", lines[start - 1]).group(1)
        if start == end:
            lines[start - 1] = indent + new_call + "\n"
        else:
            # Multi-line call: replace span with optionally wrapped call
            if len(new_call) > 88:
                lines[start - 1 : end] = [indent + new_call + "\n"]
            else:
                lines[start - 1 : end] = [indent + new_call + "\n"]

    source = "".join(lines)
    if "sanitize_log_value(" in source:
        source = _ensure_import(source)

    if source == original:
        return False
    if not dry_run:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
    return True


def iter_py_files(root: str) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def main(argv: List[str]) -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dry_run = "--dry-run" in argv
    changed: List[str] = []
    errors: List[str] = []
    for path in iter_py_files(root):
        rel = os.path.relpath(path, root)
        if rel.startswith("scripts/fix_log_injection"):
            continue
        try:
            if fix_file(path, dry_run=dry_run):
                changed.append(rel)
        except SyntaxError as exc:
            errors.append(f"{rel}: {exc}")
    print(f"{'Would change' if dry_run else 'Changed'} {len(changed)} files")
    for rel in sorted(changed):
        print(f"  {rel}")
    if errors:
        print(f"Errors ({len(errors)}):")
        for err in errors:
            print(f"  {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
