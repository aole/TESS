from nicegui import ui
import urllib.parse

# State - Text content persists across navigation
html_content = """<h2>Hello World</h2>"""

def create_page():
    
    # Logic
    def update_preview(e):
        global html_content
        html_content = e.value
        preview.run_method('setAttribute', 'srcdoc', e.value)

    # Layout
    with ui.column().classes('w-full h-[calc(100vh-4rem)] pt-4 px-4 max-w-[100%] mx-auto'):

        with ui.grid(columns=2).classes('w-full h-full gap-4'):
            # Left Column: Code Editor
            with ui.card().classes('w-full h-full glass-panel flex flex-col p-0 overflow-hidden'):

                editor = ui.codemirror(value=html_content, on_change=update_preview, language='HTML').classes('w-full flex-grow font-mono text-sm')
                editor.props('theme=dracula')

                # Helper functions for toolbar
                async def handle_upload(e):
                    try:
                        # e.file is the file object, read() is async and returns bytes
                        bytes_content = await e.file.read()
                        
                        # Try to decode as utf-8, fallback to latin-1
                        try:
                            content = bytes_content.decode('utf-8')
                        except UnicodeDecodeError:
                            content = bytes_content.decode('latin-1')
                        
                        # Update global state
                        global html_content
                        html_content = content
                        
                        # Update Editor and Preview
                        editor.value = content # Direct property update is more reliable
                        update_preview(type("Event", (), {"value": content})) 
                        
                        open_dialog.close()
                        ui.notify('File loaded successfully', type='success')
                    except Exception as err:
                        ui.notify(f'Failed to open file: {str(err)}', type='negative')

                def save_file():
                    # Get current content from global or editor
                    current_content = html_content
                    ui.download(current_content.encode('utf-8'), 'playground.html')

                def run_tab():
                    # Use JS to open new window and write content to avoid data: URL restrictions
                    # Encode content to avoid JS syntax errors
                    encoded = urllib.parse.quote(html_content)
                    ui.run_javascript(f'''
                        const win = window.open("", "_blank");
                        win.document.write(decodeURIComponent("{encoded}"));
                        win.document.close();
                    ''')

                # Open File Dialog
                with ui.dialog() as open_dialog, ui.card().classes('glass-panel p-6 w-96'):
                    ui.label('Select HTML File').classes('text-lg font-bold mb-4 text-center w-full')
                    # Use a cleaner upload appearance
                    ui.upload(on_upload=handle_upload, auto_upload=True, label='Choose File').props('accept=.html,.txt,.htm max-files=1 color=primary flat').classes('w-full')
                    ui.button('Cancel', on_click=open_dialog.close).props('flat color=grey').classes('w-full mt-2')

                # Toolbar
                with ui.row().classes('w-full p-2 gap-2 bg-white/5 border-t border-white/10 items-center justify-between'):
                    with ui.row().classes('gap-2 items-center flex-grow'):
                         ui.button(icon='folder_open', on_click=open_dialog.open).props('flat dense color=primary').tooltip('Open File')
                         ui.button(icon='save', on_click=save_file).props('flat dense color=primary').tooltip('Save File')
                         
                         ui.separator().props('vertical').classes('mx-2 h-8')
                         
                         prompt_input = ui.input(placeholder='Ask AI to edit...').classes('flex-grow').props('dense outlined rounded input-class=text-white')
                         ui.button(icon='send').props('flat dense color=secondary').tooltip('Submit Request')

                    ui.button(icon='open_in_new', on_click=run_tab).props('flat dense color=secondary').tooltip('Run in New Tab')

            # Right Column: Preview
            with ui.card().classes('w-full h-full glass-panel flex flex-col p-0 overflow-hidden bg-white/5'):

                # Use a specific container for the HTML preview to control its environment slightly better if needed
                with ui.element('div').classes('w-full h-full p-0 overflow-hidden bg-white') as preview_container:
                     preview = ui.element('iframe').classes('w-full h-full border-none')
                     # Set initial content safely
                     ui.timer(0.1, lambda: preview.run_method('setAttribute', 'srcdoc', html_content), once=True)
