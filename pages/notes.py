from nicegui import ui
from services.note_service import note_service
from datetime import datetime

def create_page():
    # Page Container
    with ui.column().classes('w-full max-w-[1000px] mx-auto p-6 gap-6'):
        
        # Header
        with ui.row().classes('w-full justify-between items-center'):
            with ui.column().classes('gap-0'):
                ui.label('Notes').classes('text-3xl font-bold text-gray-200')
                ui.label('Capture your thoughts and ideas').classes('text-sm text-gray-400')
        
        # Input Area
        with ui.card().classes('w-full p-0 gap-0 bg-[#1e1f20] border border-white/10 rounded-xl overflow-hidden'):
            with ui.column().classes('w-full p-4 gap-2'):
                note_input = ui.textarea(placeholder='What\'s on your mind?').props('autogrow borderless text-color=white input-class="text-lg"').classes('w-full')
            
                with ui.row().classes('w-full justify-between items-center pt-2 border-t border-white/5'):
                     ui.label(datetime.now().strftime("%B %d, %Y")).classes('text-xs text-gray-500 pl-1')
                     ui.button('Save Note', on_click=lambda: add_note()).props('flat no-caps icon=save color=primary')




        # Input Handling
        note_input.on('keydown.enter.exact', 
            lambda e: add_note() if not e.args['shiftKey'] else None,
            args=['shiftKey']
        )
        
        # Also allow manual button click
        # (The button is defined above but we might move the logic or just keep it)

        # Notes List
        notes_container = ui.column().classes('w-full gap-0') # Extremely compact

        def format_date(iso_str):
            try:
                dt = datetime.fromisoformat(iso_str)
                # Format: 26-Jan-26 23:54
                return dt.strftime("%d-%b-%y %H:%M")
            except:
                return iso_str

        def refresh_notes():
            notes_container.clear()
            notes = note_service.get_notes()
            
            with notes_container:
                if not notes:
                    with ui.column().classes('w-full items-center justify-center py-12 opacity-50'):
                        ui.icon('edit_note', size='48px').classes('text-gray-500 mb-2')
                        ui.label('No notes yet').classes('text-gray-500')
                
                for note in notes:
                    # Compact row layout
                    with ui.row().classes('w-full items-start group relative p-1 hover:bg-white/5 rounded transition-colors gap-2'):
                        # Timestamp + Content
                        ts = format_date(note['timestamp'])
                        content = note['content']
                        
                        # Escape content to prevent HTML injection
                        import html
                        safe_content = html.escape(content)
                        
                        ui.html(f'''
                            <div class="text-sm text-gray-200 font-sans break-words overflow-hidden">
                                <span class="text-purple-400 font-mono text-xs mr-1 opacity-80">{ts}:</span>
                                <span class="whitespace-pre-wrap">{safe_content}</span>
                            </div>
                        ''', sanitize=False).classes('flex-grow') # Removed py-1

                        # Delete action (appearing on hover)
                        # Absolute positioning to right, slightly adjusted for tighter layout
                        ui.button(icon='close', on_click=lambda _, n=note: delete_note(n['id'])).props('flat round dense size=xs color=grey').classes('opacity-0 group-hover:opacity-100 transition-opacity absolute right-1 top-1')

        def add_note():
            content = note_input.value.strip()
            if content:
                note_service.add_note(content)
                note_input.value = ''
                refresh_notes()
                ui.notify('Note saved', type='positive')

        def delete_note(note_id):
            note_service.delete_note(note_id)
            refresh_notes()
            ui.notify('Note deleted', type='info')

        # Initial Load
        refresh_notes()
