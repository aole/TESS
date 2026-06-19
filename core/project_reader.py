#!/usr/bin/env python3
"""
Standalone project reader.

Usage:
  python project_reader.py /path/to/project
  python project_reader.py /path/to/project --tree
  python project_reader.py /path/to/project --read src/main.py
  python project_reader.py /path/to/project --glob "**/*.py"
  python project_reader.py /path/to/project --grep "class\\s+Task"
  python project_reader.py /path/to/project --grep "TODO|FIXME" --include "**/*.py"
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable


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

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".scss",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".java",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".php",
    ".rb",
    ".xml",
    ".ini",
    ".cfg",
}


SPECIAL_TEXT_FILES = {
    "dockerfile",
    "makefile",
    "license",
    "readme",
    "changelog",
}

MAX_OUTPUT_LINES = 2000
MAX_LINE_LENGTH = 500


def is_ignored(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return True

    for part in rel_parts:
        if part in DEFAULT_IGNORE_DIRS:
            return True

    if path.name in DEFAULT_IGNORE_FILES:
        return True

    return False


def is_probably_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    if path.suffix == "" and path.name.lower() in SPECIAL_TEXT_FILES:
        return True

    return False


def safe_relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def resolve_inside_root(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    target = (root / relative_path).resolve()

    if target != root and root not in target.parents:
        raise ValueError("Refusing to access path outside the project folder.")

    return target


def iter_project_files(
    root: Path,
    max_file_size_kb: int,
    include_pattern: str | None = None,
) -> Iterable[Path]:
    max_bytes = max_file_size_kb * 1024

    if include_pattern:
        candidates = root.glob(include_pattern)
    else:
        candidates = root.rglob("*")

    for path in sorted(candidates):
        if is_ignored(path, root):
            continue

        if not path.is_file():
            continue

        if not is_probably_text_file(path):
            continue

        try:
            if path.stat().st_size > max_bytes:
                continue
        except OSError:
            continue

        yield path


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
            connector = "\\-- " if index == len(entries) - 1 else "+-- "
            print(prefix + connector + path.name + ("/" if path.is_dir() else ""))

            if path.is_dir():
                extension = "    " if index == len(entries) - 1 else "|   "
                walk(path, prefix + extension, depth + 1)

    walk(root)


def read_raw_file(root: Path, relative_path: str, max_file_size_kb: int) -> str:
    target = resolve_inside_root(root, relative_path)

    if not target.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")

    if not target.is_file():
        raise ValueError(f"Not a file: {relative_path}")

    if is_ignored(target, root):
        raise ValueError(f"File is ignored: {relative_path}")

    max_bytes = max_file_size_kb * 1024
    if target.stat().st_size > max_bytes:
        raise ValueError(f"File is larger than {max_file_size_kb} KB: {relative_path}")

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return target.read_text(encoding="utf-8", errors="replace")


def truncate_line(line: str) -> str:
    if len(line) <= MAX_LINE_LENGTH:
        return line
    return line[:MAX_LINE_LENGTH] + "..."


def format_numbered_lines(lines: list[tuple[int, str]]) -> str:
    if not lines:
        return "File is empty."

    output_lines = [
        f"{line_number}|{truncate_line(line)}"
        for line_number, line in lines[:MAX_OUTPUT_LINES]
    ]

    if len(lines) > MAX_OUTPUT_LINES:
        output_lines.append("...")

    return "\n".join(output_lines)


def read_file(
    root: Path,
    relative_path: str,
    max_file_size_kb: int,
    line_offset: int = 0,
    line_limit: int | None = None,
) -> str:
    if line_offset < 0:
        raise ValueError("line_offset must be non-negative.")
    if line_limit is not None and line_limit < 0:
        raise ValueError("line_limit must be non-negative.")

    content = read_raw_file(root, relative_path, max_file_size_kb)
    lines = list(enumerate(content.splitlines(), start=1))

    if line_offset:
        lines = lines[line_offset:]
    if line_limit is not None:
        lines = lines[:line_limit]

    return format_numbered_lines(lines)


def print_line_numbered_file(
    root: Path,
    relative_path: str,
    max_file_size_kb: int,
    line_offset: int = 0,
    line_limit: int | None = None,
) -> None:
    print(read_file(root, relative_path, max_file_size_kb, line_offset, line_limit))


def glob_paths(root: Path, pattern: str, include_dirs: bool = True) -> None:
    root = root.resolve()

    for path in sorted(root.glob(pattern)):
        if is_ignored(path, root):
            continue

        if not include_dirs and path.is_dir():
            continue

        print(safe_relative_path(path, root) + ("/" if path.is_dir() else ""))


def grep_repository(
    root: Path,
    regex: str,
    max_file_size_kb: int,
    include_pattern: str | None = None,
    ignore_case: bool = False,
    context: int = 0,
) -> None:
    flags = re.MULTILINE
    if ignore_case:
        flags |= re.IGNORECASE

    try:
        pattern = re.compile(regex, flags)
    except re.error as exc:
        raise SystemExit(f"Invalid regex: {exc}")

    root = root.resolve()
    first_match = True

    for path in iter_project_files(root, max_file_size_kb, include_pattern):
        rel = safe_relative_path(path, root)

        try:
            content = read_raw_file(root, rel, max_file_size_kb)
        except Exception:
            continue

        lines = content.splitlines()

        matched_line_numbers: set[int] = set()

        for index, line in enumerate(lines):
            if pattern.search(line):
                start = max(0, index - context)
                end = min(len(lines), index + context + 1)

                for line_index in range(start, end):
                    matched_line_numbers.add(line_index)

        if matched_line_numbers:
            if not first_match:
                print()
            print(f"==> {rel} <==")
            numbered_lines = [
                (line_index + 1, lines[line_index])
                for line_index in sorted(matched_line_numbers)
            ]
            print(format_numbered_lines(numbered_lines))
            first_match = False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="See project structure, read files, glob paths, and grep repository text."
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
        metavar="FILE",
        help="Read a single file with line numbers, e.g. --read src/main.py",
    )

    parser.add_argument(
        "--line-offset",
        type=int,
        default=0,
        help="Skip this many lines before returning file content with --read",
    )

    parser.add_argument(
        "--line-limit",
        type=int,
        help="Return at most this many lines with --read",
    )

    parser.add_argument(
        "--glob",
        metavar="PATTERN",
        help='Discover paths by glob pattern, e.g. --glob "**/*.py"',
    )

    parser.add_argument(
        "--grep",
        metavar="REGEX",
        help='Regex search over repository text, e.g. --grep "class\\s+Task"',
    )

    parser.add_argument(
        "--include",
        metavar="PATTERN",
        help='Limit grep to a glob pattern, e.g. --include "**/*.py"',
    )

    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Use case-insensitive regex search with --grep",
    )

    parser.add_argument(
        "--context",
        type=int,
        default=0,
        help="Show N lines of context around grep matches",
    )

    parser.add_argument(
        "--files-only",
        action="store_true",
        help="With --glob, only show files, not directories",
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
        help="Max size per file to read/search",
    )

    args = parser.parse_args()

    root = Path(args.project_path).expanduser().resolve()

    if not root.exists():
        raise SystemExit(f"Project path does not exist: {root}")

    if not root.is_dir():
        raise SystemExit(f"Project path is not a directory: {root}")

    did_something = False

    if args.tree:
        print_tree(root, args.max_depth)
        did_something = True

    if args.read:
        print_line_numbered_file(
            root,
            args.read,
            args.max_file_size_kb,
            line_offset=args.line_offset,
            line_limit=args.line_limit,
        )
        did_something = True

    if args.glob:
        glob_paths(root, args.glob, include_dirs=not args.files_only)
        did_something = True

    if args.grep:
        grep_repository(
            root=root,
            regex=args.grep,
            max_file_size_kb=args.max_file_size_kb,
            include_pattern=args.include,
            ignore_case=args.ignore_case,
            context=max(0, args.context),
        )
        did_something = True

    if not did_something:
        print_tree(root, args.max_depth)


if __name__ == "__main__":
    main()
