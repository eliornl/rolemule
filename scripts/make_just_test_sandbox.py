#!/usr/bin/env python3
"""
Create a sibling copy of the repo for safe Just / Docker tests.

Default destination: <parent>/rolemule-just-sandbox
  - Separate folder from your main clone
  - Fresh .env (does not touch your real .env)
  - `just start` there uses a different Docker Compose project name → separate DB volumes

Usage:
  python3 scripts/make_just_test_sandbox.py
  python3 scripts/make_just_test_sandbox.py --dest /path/to/my-copy
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Names excluded at any level (basename match).
_SKIP_NAMES = frozenset(
    {
        ".git",
        ".cursor",
        "_private",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "htmlcov",
        ".mypy_cache",
        ".env",
        ".env.local",
        ".coverage",
        ".DS_Store",
        "rolemule-just-sandbox",
        "sandbox-just-test",
    }
)


def _ignore(dirpath: str, names: list[str]) -> set[str]:
    skip: set[str] = set()
    base = Path(dirpath).name
    for name in names:
        if name in _SKIP_NAMES:
            skip.add(name)
        if name.endswith(".egg-info"):
            skip.add(name)
        if base == "ui" and name == "node_modules":
            skip.add(name)
    return skip


def _copy_repo(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore, symlinks=False)


def _write_readme(dst: Path) -> None:
    dest_line = str(dst)
    text = f"""# RoleMule — Just / Docker test sandbox

This tree was created by `scripts/make_just_test_sandbox.py`.

## Your real project is untouched

- No changes to your original repo `.env` or database.
- This folder has its **own** `.env` (auto-generated).

## What to run here (macOS)

```bash
cd {dest_line}
just --list
just start             # needs Docker; own Compose project + volumes (stop your main stack first if ports 8000/5432 clash)
```

## If `just start` says ports are in use

Stop the other stack (`docker compose down` in the other repo) or change published ports only in **this** copy’s `docker-compose.yml`.

## Remove when done

```bash
rm -rf {dest_line}
```
"""
    (dst / "SANDBOX_README.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone repo tree for Just/Docker testing.")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Destination directory (default: sibling rolemule-just-sandbox)",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parent.parent
    dest = args.dest if args.dest is not None else repo.parent / "rolemule-just-sandbox"

    print(f"Source: {repo}")
    print(f"Destination: {dest}")
    _copy_repo(repo, dest)
    _write_readme(dest)

    r = subprocess.run(
        [sys.executable, str(dest / "scripts" / "create_dotenv_if_missing.py")],
        cwd=str(dest),
        check=False,
    )
    if r.returncode != 0:
        print("Warning: create_dotenv_if_missing.py failed; create .env manually.", file=sys.stderr)
        sys.exit(r.returncode)

    print("")
    print("Done. Next:")
    print(f"  cd {dest}")
    print("  just --list")
    print("  just start    # optional; uses separate Docker project from this path")


if __name__ == "__main__":
    main()
