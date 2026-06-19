from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from core.project_reader import print_tree


def read_project_tree(project_path: str = ".", max_depth: int = 4) -> str:
    """
    Return an ASCII tree view of a local project directory.

    Args:
        project_path: Root folder to inspect. Defaults to the current workspace.
        max_depth: Maximum folder depth to include in the tree.

    Returns:
        A newline-delimited tree view of the project.
    """
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        return f"Error: Project path does not exist: {root}"
    if not root.is_dir():
        return f"Error: Project path is not a directory: {root}"

    buffer = StringIO()
    with redirect_stdout(buffer):
        print_tree(root, max_depth=max_depth)
    return buffer.getvalue().strip()
