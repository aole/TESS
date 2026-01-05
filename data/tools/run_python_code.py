import sys
import io
import ast
import traceback
from typing import List, Optional

def run_python_code(code: str, args: Optional[List[str]] = None) -> str:
    """
    Execute arbitrary Python code and return the output or result.
    
    This tool can execute both scripts (multiple statements) and single expressions.
    - If a single expression is provided (e.g., "2 + 2", "pow(5, 3)"), it evaluates and returns the result.
    - If a script is provided (e.g., imports, loops, print statements), it executes it and captures stdout.
    
    IMPORTANT:
    - This is NOT a bash shell. accessing files or system commands requires importing 'os' or 'subprocess'.
    - Math usage: Use '**' for power (e.g. 2**3 = 8), NOT '^'.
    - The code runs in the current process.
    - JSON FORMATTING: When writing code strings, do NOT escape characters that don't need it (like '?'). Only escape double quotes (\") and backslashes (\\).

    Args:
        code (str): The valid Python code or expression to execute.
        args (list, optional): Arguments exposed as 'sys.argv' for the script.

    Returns:
        str: The result of the expression, or the standard output of the script, or an error message.
    """
    # Create a captive stdout
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output

    try:
        # 1. Try to parse and evaluate as a single expression first
        try:
            tree = ast.parse(code)
            if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
                # It's an expression
                code_obj = compile(code, '<string>', 'eval')
                result = eval(code_obj, {}, {})
                return str(result)
        except SyntaxError:
            pass # Fallback to exec

        # 2. Execute as a script/block
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
