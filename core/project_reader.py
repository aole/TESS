#!/usr/bin/env python3
"""
Standalone project reader.

Usage:
  python project_reader.py /path/to/project
  python project_reader.py /path/to/project --tree
  python project_reader.py /path/to/project --read src/main.py
"""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".cache",
}

DEFAULT_IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
}


def is_ignored(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts

    for part in rel_parts:
        if part in DEFAULT_IGNORE_DIRS:
            return True

    if path.name in DEFAULT_IGNORE_FILES:
        return True

    return False


def print_tree(root: Path, max_depth: int = 4) -> None:
    root = root.resolve()
    print(root.name + "/")

    def walk(directory: Path, prefix: str = "", depth: int = 0) -> None:
        if depth >= max_depth:
            return

        try:
            entries = sorted(
                [p for p in directory.iterdir() if not is_ignored(p, root)],
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except PermissionError:
            return

        for index, path in enumerate(entries):
            connector = "└── " if index == len(entries) - 1 else "├── "
            print(prefix + connector + path.name + ("/" if path.is_dir() else ""))

            if path.is_dir():
                extension = "    " if index == len(entries) - 1 else "│   "
                walk(path, prefix + extension, depth + 1)

    walk(root)


def read_file(root: Path, relative_path: str, max_file_size_kb: int) -> str:
    root = root.resolve()
    target = (root / relative_path).resolve()

    if not str(target).startswith(str(root)):
        raise ValueError("Refusing to read outside the project folder.")

    if not target.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")

    if not target.is_file():
        raise ValueError(f"Not a file: {relative_path}")

    max_bytes = max_file_size_kb * 1024
    if target.stat().st_size > max_bytes:
        raise ValueError(f"File is larger than {max_file_size_kb} KB: {relative_path}")

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return target.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="See project structure and read selected files."
    )

    parser.add_argument(
        "project_path",
        help="Path to the local GitHub/project folder",
    )

    parser.add_argument(
        "--tree",
        action="store_true",
        help="Print project tree",
    )

    parser.add_argument(
        "--read",
        help="Read a single file by relative path, e.g. --read src/main.py",
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Max folder depth for tree output",
    )

    parser.add_argument(
        "--max-file-size-kb",
        type=int,
        default=256,
        help="Max size per file to read",
    )

    args = parser.parse_args()

    root = Path(args.project_path).expanduser().resolve()

    if not root.exists():
        raise SystemExit(f"Project path does not exist: {root}")

    if not root.is_dir():
        raise SystemExit(f"Project path is not a directory: {root}")

    if args.tree:
        print_tree(root, args.max_depth)

    if args.read:
        content = read_file(root, args.read, args.max_file_size_kb)
        print(content)

    if not args.tree and not args.read:
        print_tree(root, args.max_depth)


if __name__ == "__main__":
    main()
