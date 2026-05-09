from nicegui import ui
from pathlib import Path

def render():
    with ui.column().classes('w-full max-w-3xl mx-auto mt-8 gap-6'):        
        md_file_path = Path(__file__).parent / 'tutorial.md'
        with open(md_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        ui.markdown(content).classes('text-base text-gray-300 leading-relaxed')
