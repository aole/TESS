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

        with ui.card().classes('w-full p-6 bg-black/20 border-white/5'):
            ui.label('Rating Tags').classes('text-xl font-bold mb-4 text-gray-200')
            
            # Container for tags
            tags_container = ui.row().classes('gap-2 mb-4')
            
            def render_tags():
                tags_container.clear()
                with tags_container:
                    for tag in config_manager.get_rating_tags():
                        c = ui.chip(removable=True, icon='label', color='indigo-9')
                        c.classes('text-indigo-200')
                        c.on('remove', lambda _, t=tag: remove_tag(t))
                        with c:
                            ui.label(tag)

            def add_tag():
                new_tag = tag_input.value.strip()
                if new_tag:
                    config_manager.add_rating_tag(new_tag)
                    tag_input.value = ''
                    render_tags()

            def remove_tag(tag):
                config_manager.remove_rating_tag(tag)
                render_tags()

            with ui.row().classes('items-center gap-2'):
                tag_input = ui.input(placeholder='New Tag Name').classes('w-64').on('keydown.enter', add_tag)
                ui.button(icon='add', on_click=add_tag).props('flat round color=secondary')
            
            render_tags()
