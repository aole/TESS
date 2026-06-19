from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from core.project_reader import grep_repository


def grep_project_text(
    regex: str,
    project_path: str = ".",
    include_pattern: str | None = None,
    ignore_case: bool = False,
    context: int = 0,
    max_file_size_kb: int = 256,
) -> str:
    """
    Search text files in a project with a regular expression.

    Args:
        regex: Regular expression to search for.
        project_path: Root folder to inspect. Defaults to the current workspace.
        include_pattern: Optional glob that limits which files are searched.
        ignore_case: When true, perform a case-insensitive search.
        context: Number of context lines to include around each match.
        max_file_size_kb: Maximum file size to inspect.

    Returns:
        Matching lines grouped by file, with content lines in ``LINE_NUMBER|LINE_CONTENT`` format,
        or an error message.
    """
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        return f"Error: Project path does not exist: {root}"
    if not root.is_dir():
        return f"Error: Project path is not a directory: {root}"

    buffer = StringIO()
    try:
        with redirect_stdout(buffer):
            grep_repository(
                root=root,
                regex=regex,
                max_file_size_kb=max_file_size_kb,
                include_pattern=include_pattern,
                ignore_case=ignore_case,
                context=max(0, context),
            )
    except SystemExit as exc:
        return f"Error: {exc}"

    return buffer.getvalue().strip()
