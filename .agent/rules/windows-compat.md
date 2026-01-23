---
trigger: always_on
---

The user is running on Windows. Ensure all terminal commands are compatible with Windows PowerShell. Avoid Unix-specific commands like `sudo`, `export` (use `$env:VAR='val'`), or assuming forward slashes in paths if manual command construction is tricky (though PowerShell is forgiving). Always prefer PowerShell syntax.
