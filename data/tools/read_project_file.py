from pathlib import Path

from core.project_reader import read_file


def read_project_file(
    relative_path: str,
    project_path: str = ".",
    max_file_size_kb: int = 256,
    line_offset: int = 0,
    line_limit: int | None = None,
) -> str:
    """
    Read a text file from within a project folder.

    Args:
        relative_path: File path relative to the project root.
        project_path: Root folder to inspect. Defaults to the current workspace.
        max_file_size_kb: Maximum allowed file size to read.
        line_offset: Optional number of lines to skip before returning content.
        line_limit: Optional maximum number of lines to return after the offset.

    Returns:
        Numbered file contents in ``LINE_NUMBER|LINE_CONTENT`` format, or an error message.

    Usage:
        You can optionally specify ``line_offset`` and ``line_limit`` for long files,
        but it is recommended to read the whole file by leaving them unset.
    """
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        return f"Error: Project path does not exist: {root}"
    if not root.is_dir():
        return f"Error: Project path is not a directory: {root}"

    try:
        return read_file(
            root,
            relative_path,
            max_file_size_kb,
            line_offset=line_offset,
            line_limit=line_limit,
        )
    except Exception as exc:
        return f"Error: {exc}"
