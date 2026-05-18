import asyncio
import os
import sys
import subprocess
from nicegui import ui, app

# Constants
PYTHON_SCRIPT_FILE = 'data/python/script.py'

def load_code():
    if not os.path.exists(PYTHON_SCRIPT_FILE):
        try:
            os.makedirs(os.path.dirname(PYTHON_SCRIPT_FILE), exist_ok=True)
            default_code = 'print("Hello from Python IDE!")\n'
            with open(PYTHON_SCRIPT_FILE, 'w', encoding='utf-8') as f:
                f.write(default_code)
            return default_code
        except Exception as e:
            print(f"Error creating default python script: {e}")
            return 'print("Hello from Python IDE!")\n'
    try:
        with open(PYTHON_SCRIPT_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return 'print("Hello from Python IDE!")\n'

python_code = load_code()

def create_page():
    process = None
    
    def save_code(e):
        global python_code
        python_code = e.value
        try:
            with open(PYTHON_SCRIPT_FILE, 'w', encoding='utf-8') as f:
                f.write(python_code)
        except Exception:
            pass

    async def run_code():
        nonlocal process
        if process and process.poll() is None:
            output_log.push("Process is already running.")
            return

        # Clear output before the next run
        output_log.clear()

        status_badge.set_text("Running")
        status_badge.props('color=green')
        
        output_log.push(f"> Executing {PYTHON_SCRIPT_FILE}...")
        
        # Save before running
        try:
            with open(PYTHON_SCRIPT_FILE, 'w', encoding='utf-8') as f:
                f.write(python_code)
        except Exception as e:
            output_log.push(f"Error saving file: {e}")
            
        # Configure env to include current working directory in PYTHONPATH
        env = os.environ.copy()
        cwd = os.getcwd()
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = cwd + os.pathsep + env['PYTHONPATH']
        else:
            env['PYTHONPATH'] = cwd

        process = subprocess.Popen(
            [sys.executable, '-u', PYTHON_SCRIPT_FILE],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, process.stdout.readline)
            if not line:
                break
            output_log.push(line.rstrip())
            
        await loop.run_in_executor(None, process.wait)
        status_badge.set_text("Idle")
        status_badge.props('color=grey')
        output_log.push(f"> Process exited with code {process.returncode}")

    def stop_code():
        nonlocal process
        if process and process.poll() is None:
            process.terminate()
            output_log.push("> Process terminated by user.")
            status_badge.set_text("Idle")
            status_badge.props('color=grey')

    def clear_output():
        output_log.clear()

    def create_tool_from_code():
        app.storage.user['pending_tool_code'] = python_code
        ui.navigate.to('/tools')

    async def run_terminal_command():
        cmd = terminal_input.value
        if not cmd: return
        terminal_input.value = ''
        output_log.push(f"$ {cmd}")
        
        # Configure env to include current working directory in PYTHONPATH
        env = os.environ.copy()
        cwd = os.getcwd()
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = cwd + os.pathsep + env['PYTHONPATH']
        else:
            env['PYTHONPATH'] = cwd

        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            text=True,
            bufsize=1,
            env=env,
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, p.stdout.readline)
            if not line:
                break
            output_log.push(line.rstrip())
            
        await loop.run_in_executor(None, p.wait)
        output_log.push(f"> Command exited with code {p.returncode}")

    with ui.column().classes('w-full h-[calc(100vh-4rem)] pt-4 px-4 max-w-[100%] mx-auto'):
        # Toolbar
        with ui.row().classes('w-full items-center justify-between glass-panel p-2 rounded-lg'):
            with ui.row().classes('gap-2 items-center'):
                ui.button('Run', icon='play_arrow', on_click=run_code).props('color=positive dense')
                ui.button('Stop', icon='stop', on_click=stop_code).props('color=negative dense flat')
                ui.button('Clear Output', icon='clear_all', on_click=clear_output).props('color=secondary dense flat')
                ui.button('Create Tool', icon='build', on_click=create_tool_from_code).props('color=indigo dense flat')
            
            status_badge = ui.badge('Idle', color='grey').classes('text-sm')
            
        # Splitter
        with ui.splitter(value=60).classes('w-full flex-grow') as splitter:
            with splitter.before:
                # Code Editor
                with ui.card().classes('w-full h-full glass-panel flex flex-col p-0 overflow-hidden mr-2'):
                    editor = ui.codemirror(value=python_code, on_change=save_code, language='Python').classes('w-full flex-grow font-mono text-sm')
                    editor.props('theme=dracula')
                
            with splitter.after:
                # Output and Terminal
                with ui.column().classes('w-full h-full gap-0 ml-2'):
                    output_log = ui.log().classes('w-full flex-grow bg-[#0c0c0c] text-[#00ff00] font-mono text-sm p-2 rounded-t-lg border border-white/10')
                    
                    with ui.row().classes('w-full items-center bg-[#1e1e1e] border border-t-0 border-white/10 rounded-b-lg p-1'):
                        ui.label('$').classes('text-green-500 font-mono ml-2 font-bold')
                        terminal_input = ui.input(placeholder='Enter shell command...').classes('flex-grow px-2 font-mono text-white').props('dense borderless dark')
                        terminal_input.on('keydown.enter', run_terminal_command)
                        ui.button('Submit', on_click=run_terminal_command).props('dense flat color=green')
