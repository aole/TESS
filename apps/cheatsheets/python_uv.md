# Python UV Cheatsheet

A practical reference for using `uv` as a fast Python project manager, package manager, virtual environment manager, and `pip` replacement.

---

## 1. What is `uv`?

`uv` is a fast Python package and project manager from Astral. It can replace several common tools:

| Traditional Tool              | `uv` Replacement    |
| ----------------------------- | ------------------- |
| `pip`                         | `uv pip` / `uv add` |
| `venv`                        | `uv venv`           |
| `pip-tools`                   | `uv lock`           |
| `pipx`                        | `uv tool` / `uvx`   |
| `pyenv`-style Python installs | `uv python`         |
| manual virtualenv activation  | `uv run`            |

---

## 2. Project Setup

### Create a new project

```bash
uv init
```

Creates a new Python project in the current directory.

```bash
uv init my-app
```

Creates a new project in a new folder.

```bash
uv init --app
```

Create an application-style project.

```bash
uv init --lib
```

Create a library-style project.

```bash
uv init --script main.py
```

Create a standalone Python script with inline dependency metadata.

---

## 3. Basic Project Workflow

Typical flow:

```bash
uv init
uv add requests
uv run python main.py
```

Common commands:

| Command               | Purpose                                                       |
| --------------------- | ------------------------------------------------------------- |
| `uv init`             | Create a new Python project.                                  |
| `uv add <package>`    | Add a dependency to `pyproject.toml` and update the lockfile. |
| `uv remove <package>` | Remove a dependency from the project.                         |
| `uv run <command>`    | Run a command inside the project environment.                 |
| `uv sync`             | Install dependencies from the lockfile into the environment.  |
| `uv lock`             | Resolve dependencies and update `uv.lock` without installing. |
| `uv tree`             | Show the dependency tree.                                     |

---

## 4. Add and Remove Packages

### Add a package

```bash
uv add requests
```

### Add multiple packages

```bash
uv add requests rich pydantic
```

### Add a specific version

```bash
uv add "fastapi>=0.115"
```

```bash
uv add "numpy==2.1.0"
```

### Add a development dependency

```bash
uv add --dev pytest
```

```bash
uv add --dev ruff mypy
```

### Remove a package

```bash
uv remove requests
```

### Remove a development dependency

```bash
uv remove --dev pytest
```

---

## 5. Running Code

### Run a Python file

```bash
uv run python main.py
```

### Run a module

```bash
uv run python -m pytest
```

### Run an installed CLI tool from the project

```bash
uv run ruff check .
```

### Run with arguments

```bash
uv run python main.py --input image.png
```

### Run without manually activating `.venv`

```bash
uv run python
```

This is one of the best parts of `uv`: you usually do not need to manually activate the virtual environment.

---

## 6. Virtual Environments

### Create a virtual environment

```bash
uv venv
```

Creates `.venv` in the current directory.

### Create a venv with a specific Python version

```bash
uv venv --python 3.12
```

### Activate on Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### Activate on Windows CMD

```cmd
.venv\Scripts\activate.bat
```

### Activate on Linux/macOS

```bash
source .venv/bin/activate
```

### Deactivate

```bash
deactivate
```

Note: For most project commands, prefer `uv run` instead of activating manually.

---

## 7. Syncing and Locking

### Install exact locked dependencies

```bash
uv sync
```

Installs dependencies from `uv.lock`.

### Update the lockfile only

```bash
uv lock
```

Resolves dependencies and updates `uv.lock`, but does not install them.

### Upgrade dependencies

```bash
uv lock --upgrade
```

### Upgrade one package

```bash
uv lock --upgrade-package requests
```

### Sync after changing `pyproject.toml`

```bash
uv sync
```

### Recreate environment from lockfile

```bash
rm -rf .venv
uv sync
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force .venv
uv sync
```

---

## 8. `uv pip` Compatible Commands

Use `uv pip` when working in a more traditional `pip` workflow.

### Install a package

```bash
uv pip install requests
```

### Install from requirements file

```bash
uv pip install -r requirements.txt
```

### Uninstall a package

```bash
uv pip uninstall requests
```

### List installed packages

```bash
uv pip list
```

### Show package details

```bash
uv pip show requests
```

### Freeze installed packages

```bash
uv pip freeze
```

### Check installed package version

```bash
uv pip show requests
```

Or:

```bash
uv run python -c "import requests; print(requests.__version__)"
```

Important: `uv pip show` does not use a `--version` flag. Use `uv pip show <package>` or check from Python directly.

---

## 9. Python Version Management

### List available Python versions

```bash
uv python list
```

### Install a Python version

```bash
uv python install 3.12
```

### Pin a Python version for the project

```bash
uv python pin 3.12
```

This creates or updates the `.python-version` file.

### Use a specific Python version while running

```bash
uv run --python 3.12 python main.py
```

### Create venv with a specific Python

```bash
uv venv --python 3.12
```

---

## 10. Tools and One-Off Commands

`uv` can run tools without permanently installing them into your project.

### Run a tool temporarily

```bash
uvx ruff check .
```

Equivalent style:

```bash
uv tool run ruff check .
```

### Install a tool globally

```bash
uv tool install ruff
```

### List installed tools

```bash
uv tool list
```

### Upgrade installed tools

```bash
uv tool upgrade --all
```

### Uninstall a tool

```bash
uv tool uninstall ruff
```

Good candidates for `uv tool`:

```bash
ruff
black
mypy
httpie
cookiecutter
pre-commit
```

---

## 11. Scripts with Inline Dependencies

You can run standalone scripts without creating a full project.

### Run a script

```bash
uv run script.py
```

### Add dependencies to a script

```bash
uv add --script script.py requests rich
```

Example script metadata:

```python
# /// script
# dependencies = [
#   "requests",
#   "rich",
# ]
# ///

import requests
from rich import print

print(requests.get("https://example.com").status_code)
```

Run it:

```bash
uv run script.py
```

---

## 12. Using Requirements Files

### Install from `requirements.txt`

```bash
uv pip install -r requirements.txt
```

### Generate requirements-style output

```bash
uv pip freeze > requirements.txt
```

### Compile dependencies

```bash
uv pip compile pyproject.toml -o requirements.txt
```

---

## 13. Common `pyproject.toml` Example

```toml
[project]
name = "my-app"
version = "0.1.0"
description = "My Python app"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "requests>=2.32.0",
    "pydantic>=2.8.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.6.0",
]
```

---

## 14. Git Dependencies

### Add package from Git

```bash
uv add git+https://github.com/user/repo.git
```

### Add named Git dependency manually

```toml
[project]
dependencies = [
    "diffsynth",
]

[tool.uv.sources]
diffsynth = { git = "https://github.com/modelscope/DiffSynth-Studio.git" }
```

Then sync:

```bash
uv sync
```

### Force refresh a Git dependency

```bash
uv lock --upgrade-package diffsynth
uv sync
```

If needed:

```bash
uv cache clean
uv sync
```

---

## 15. Custom Package Indexes

Useful for PyTorch CUDA builds or private package repositories.

Example:

```toml
[project]
dependencies = [
    "torch",
    "torchvision",
    "torchaudio",
]

[tool.uv.sources]
torch = { index = "pytorch-cu126" }
torchvision = { index = "pytorch-cu126" }
torchaudio = { index = "pytorch-cu126" }

[[tool.uv.index]]
name = "pytorch-cu126"
url = "https://download.pytorch.org/whl/cu126"
explicit = true
```

Then run:

```bash
uv sync
```

---

## 16. PyTorch Example

### CPU version

```bash
uv add torch torchvision torchaudio
```

### CUDA index example

```toml
[tool.uv.sources]
torch = { index = "pytorch-cu126" }
torchvision = { index = "pytorch-cu126" }
torchaudio = { index = "pytorch-cu126" }

[[tool.uv.index]]
name = "pytorch-cu126"
url = "https://download.pytorch.org/whl/cu126"
explicit = true
```

Then:

```bash
uv sync
```

Check CUDA:

```bash
uv run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

---

## 17. Cache Commands

### Show cache directory

```bash
uv cache dir
```

### Clean entire cache

```bash
uv cache clean
```

### Clean one package from cache

```bash
uv cache clean requests
```

### Prune unused cache entries

```bash
uv cache prune
```

---

## 18. Build and Publish

### Build package

```bash
uv build
```

Creates distribution files in `dist/`.

### Publish package

```bash
uv publish
```

Usually requires credentials or trusted publishing configuration.

---

## 19. Useful Diagnostics

### Show dependency tree

```bash
uv tree
```

### Show installed packages

```bash
uv pip list
```

### Show package details

```bash
uv pip show <package>
```

### Check Python executable

```bash
uv run python -c "import sys; print(sys.executable)"
```

### Check Python version

```bash
uv run python --version
```

### Check package import path

```bash
uv run python -c "import requests; print(requests.__file__)"
```

### Check package version

```bash
uv run python -c "import requests; print(requests.__version__)"
```

---

## 20. Common Fixes

### Package added but not available

```bash
uv sync
```

Then:

```bash
uv run python main.py
```

### Lockfile is stale

```bash
uv lock
uv sync
```

### Git dependency not updating

```bash
uv lock --upgrade-package <package>
uv sync
```

If still stale:

```bash
uv cache clean
uv sync
```

### Wrong Python version

```bash
uv python list
uv python install 3.12
uv python pin 3.12
uv sync
```

### Broken virtual environment

```bash
rm -rf .venv
uv sync
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force .venv
uv sync
```

### See which Python is being used

```bash
uv run python -c "import sys; print(sys.executable)"
```

---

## 21. Recommended Daily Commands

| Task                    | Command                                          |
| ----------------------- | ------------------------------------------------ |
| Create project          | `uv init`                                        |
| Add dependency          | `uv add <package>`                               |
| Add dev dependency      | `uv add --dev <package>`                         |
| Remove dependency       | `uv remove <package>`                            |
| Run app                 | `uv run python main.py`                          |
| Run tests               | `uv run pytest`                                  |
| Sync environment        | `uv sync`                                        |
| Update lockfile         | `uv lock`                                        |
| Upgrade all packages    | `uv lock --upgrade && uv sync`                   |
| Upgrade one package     | `uv lock --upgrade-package <package> && uv sync` |
| Show dependency tree    | `uv tree`                                        |
| Show installed packages | `uv pip list`                                    |
| Show package info       | `uv pip show <package>`                          |
| Create venv             | `uv venv`                                        |
| Install Python          | `uv python install 3.12`                         |
| Pin Python              | `uv python pin 3.12`                             |

---

## 22. Mental Model

Use this split:

| Use Case                               | Prefer                                      |
| -------------------------------------- | ------------------------------------------- |
| Managing a real project                | `uv add`, `uv remove`, `uv sync`, `uv lock` |
| Running commands inside the project    | `uv run`                                    |
| Traditional pip-style environment work | `uv pip ...`                                |
| One-off CLI tools                      | `uvx` or `uv tool run`                      |
| Global developer tools                 | `uv tool install`                           |
| Managing Python versions               | `uv python ...`                             |

For normal app development, the main loop is:

```bash
uv add <package>
uv run python main.py
```

For reproducible installs:

```bash
uv sync
```

For upgrades:

```bash
uv lock --upgrade
uv sync
```
