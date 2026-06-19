from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from core.project_reader import glob_paths


def glob_project_paths(
    pattern: str,
    project_path: str = ".",
    files_only: bool = False,
) -> list[str]:
    """
    Find project paths matching a glob pattern.

    Args:
        pattern: Glob pattern such as ``"**/*.py"``.
        project_path: Root folder to inspect. Defaults to the current workspace.
        files_only: When true, omit directories from the results.

    Returns:
        A list of matching relative paths. Directory results end with ``/``.
    """
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        return [f"Error: Project path does not exist: {root}"]
    if not root.is_dir():
        return [f"Error: Project path is not a directory: {root}"]

    buffer = StringIO()
    with redirect_stdout(buffer):
        glob_paths(root, pattern, include_dirs=not files_only)

    output = buffer.getvalue().strip()
    return output.splitlines() if output else []
