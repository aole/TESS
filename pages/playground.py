from nicegui import ui

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

                editor = ui.codemirror(value=html_content, on_change=update_preview, language='HTML').classes('w-full h-full font-mono text-sm')
                editor.props('theme=dracula')

            # Right Column: Preview
            with ui.card().classes('w-full h-full glass-panel flex flex-col p-0 overflow-hidden bg-white/5'):

                # Use a specific container for the HTML preview to control its environment slightly better if needed
                with ui.element('div').classes('w-full h-full p-0 overflow-hidden bg-white') as preview_container:
                     preview = ui.element('iframe').classes('w-full h-full border-none')
                     # Set initial content safely
                     ui.timer(0.1, lambda: preview.run_method('setAttribute', 'srcdoc', html_content), once=True)
