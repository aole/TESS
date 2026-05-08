import sys
import io
import ast
import traceback
from typing import List, Optional

def run_python_code(code: str, args: Optional[List[str]] = None) -> str:
    """
    Execute arbitrary Python code and return the output.
    
    This tool executes Python scripts and captures standard output (stdout).
    YOU MUST USE `print()` statements to output any information you want to receive back!
    If your code does not print anything, the tool will return an empty string.
    
    IMPORTANT:
    - This is NOT a bash shell. accessing files or system commands requires importing 'os' or 'subprocess'.
    - Math usage: Use '**' for power (e.g. 2**3 = 8), NOT '^'.
    - The code runs in the current process.
    - JSON FORMATTING: When writing code strings, do NOT escape characters that don't need it (like '?'). Only escape double quotes (\") and backslashes (\\).

    Args:
        code (str): The valid Python code or expression to execute.
        args (list, optional): Arguments exposed as 'sys.argv' for the script.

    Returns:
        str: the standard output of the script, or an error message.
    """
    # Create a captive stdout
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output

    try:
        # Execute as a script/block
        exec_globals = {}
        if args:
            exec_globals['sys'] = sys
            sys.argv = ['<string>'] + args
        
        exec(code, exec_globals)
        return redirected_output.getvalue()

    except Exception:
        return traceback.format_exc()
    finally:
        sys.stdout = old_stdout
