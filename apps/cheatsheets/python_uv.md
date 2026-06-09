# Python UV Cheatsheet

- **uv init** - Create a new Python project in the current directory.
- **uv add <package>** - Add a dependency to the project and update the lockfile.
- **uv remove <package>** - Remove a dependency from the project.
- **uv run <command>** - Run a command in the project environment without manual activation.
- **uv sync** - Install the exact locked dependencies into the environment.
- **uv lock** - Resolve and update the lockfile without installing packages.
- **uv pip install <package>** - Install a package using uv's pip-compatible workflow.
- **uv venv** - Create a virtual environment for the current project.
