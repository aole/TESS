from nicegui import ui
from utils.config import config_manager
from services.note_service import note_service

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

        with ui.card().classes('w-full p-6 bg-black/20 border-white/5'):
            ui.label('Note Categories').classes('text-xl font-bold mb-4 text-gray-200')
            
            # Container for categories
            cats_container = ui.row().classes('gap-2 mb-4')
            
            def render_cats():
                cats_container.clear()
                with cats_container:
                    for cat in config_manager.get_note_categories():
                        c = ui.chip(removable=True, icon='folder', color='emerald-9')
                        c.classes('text-emerald-200')
                        c.on('remove', lambda _, t=cat: remove_cat(t))
                        with c:
                            ui.label(cat)

            def add_cat():
                new_cat = cat_input.value.strip()
                if new_cat:
                    config_manager.add_note_category(new_cat)
                    cat_input.value = ''
                    render_cats()

            def remove_cat(cat):
                config_manager.remove_note_category(cat)
                render_cats()

            with ui.row().classes('items-center gap-2'):
                cat_input = ui.input(placeholder='New Category').classes('w-64').on('keydown.enter', add_cat)
                ui.button(icon='add', on_click=add_cat).props('flat round color=secondary')
            
            render_cats()
            
            ui.separator().classes('my-4 bg-white/10')
            
            ui.label('Storage Location').classes('text-sm font-bold text-gray-400 mb-2')
            
            def handle_storage_change(e):
                new_val = e.value
                old_val = config_manager.get_note_storage()
                
                if new_val == old_val:
                    return

                # Create Dialog
                with ui.dialog() as dialog, ui.card().classes('bg-[#1e1f20] border border-white/10 p-6 w-96'):
                    ui.label('Sync Notes?').classes('text-xl font-bold text-gray-200 mb-2')
                    ui.label('Merge existing notes from both locations?').classes('text-gray-400 text-sm mb-6')
                    
                    with ui.row().classes('w-full justify-end gap-2'):
                        async def do_sync():
                            dialog.close()
                            ui.notify('Syncing...', type='info')
                            try:
                                # Run sync in background to avoid blocking UI if drive is slow
                                from nicegui import run
                                count = await run.io_bound(note_service.sync_notes)
                                config_manager.set_note_storage(new_val)
                                ui.notify(f'Synced {count} notes using {new_val}', type='positive')
                            except Exception as ex:
                                ui.notify(f'Sync failed: {ex}', type='negative')
                                storage_select.value = old_val

                        def just_switch():
                            dialog.close()
                            config_manager.set_note_storage(new_val)
                            ui.notify(f'Switched to {new_val}', type='positive')

                        def cancel():
                            dialog.close()
                            storage_select.value = old_val # Revert

                        ui.button('Cancel', on_click=cancel).props('flat color=grey')
                        ui.button('Switch Only', on_click=just_switch).props('flat color=warning')
                        ui.button('Sync & Switch', on_click=do_sync).props('flat color=primary')
                
                dialog.open()

            storage_select = ui.select(['local', 'google_drive'], 
                      label='Save Notes To',
                      value=config_manager.get_note_storage(),
                      on_change=handle_storage_change).classes('w-full')
            
        # Playground Settings
        with ui.card().classes('w-full p-6 bg-black/20 border-white/5'):
            ui.label('Playground Configuration').classes('text-xl font-bold mb-4 text-indigo-400')
            
            # We need to import client inside function or top of file, doing top of file import is cleaner usually but let's check
            # Adding import at top would be best but this tool replaces blocks.
            # I will insert the import at top and the block here.
            
            async def load_models_for_setting():
                from utils.ollama_client import client
                try:
                    models_list = await client.list_models()
                    options = [m['model'] for m in models_list]
                    model_select.options = options
                    # Load saved setting if available (mocked for now)
                    if options and not model_select.value:
                        model_select.value = options[0]
                except:
                    pass

            model_select = ui.select(options=[], label='AI Assistant Model').classes('w-full')
            ui.timer(0.1, load_models_for_setting, once=True)
