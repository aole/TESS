from pathlib import Path

from core.project_reader import read_file


def read_project_file(
    relative_path: str,
    project_path: str = ".",
    max_file_size_kb: int = 256,
) -> str:
    """
    Read a text file from within a project folder.

    Args:
        relative_path: File path relative to the project root.
        project_path: Root folder to inspect. Defaults to the current workspace.
        max_file_size_kb: Maximum allowed file size to read.

    Returns:
        The file contents, or an error message if the file cannot be read.
    """
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        return f"Error: Project path does not exist: {root}"
    if not root.is_dir():
        return f"Error: Project path is not a directory: {root}"

    try:
        return read_file(root, relative_path, max_file_size_kb)
    except Exception as exc:
        return f"Error: {exc}"
