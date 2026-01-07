from nicegui import ui
from utils.config import config_manager

def create_page():
    with ui.column().classes('w-full max-w-3xl mx-auto p-8 gap-8'):
        ui.label('Settings').classes('text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400')
        
        with ui.card().classes('w-full p-6 bg-black/20 border-white/5'):
            ui.label('Logging Configuration').classes('text-xl font-bold mb-4 text-gray-200')
            
            with ui.column().classes('gap-4'):
                ui.checkbox('Enable Chat Logging', 
                            value=config_manager.is_logging_enabled('chat'),
                            on_change=lambda e: config_manager.set_logging('chat', e.value)).classes('text-gray-300')
                
                ui.checkbox('Enable Arena Logging', 
                            value=config_manager.is_logging_enabled('arena'),
                            on_change=lambda e: config_manager.set_logging('arena', e.value)).classes('text-gray-300')
                
                ui.checkbox('Enable Batch Logging', 
                            value=config_manager.is_logging_enabled('batch'),
                            on_change=lambda e: config_manager.set_logging('batch', e.value)).classes('text-gray-300')
                
            ui.markdown('> Logs are saved to `logs/llm_debug.log`').classes('mt-4 text-sm text-gray-500 italic')
