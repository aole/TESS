from nicegui import ui, app
from pages import models, chat, arena, batch, tools, create, settings

# Page styling and configuration
# Page styling and configuration
def layout(page_path: str = ''):
    ui.add_head_html("""
        <style>
            :root {
                --nicegui-default-padding: 0.1rem;
                --nicegui-default-gap: 0.1rem;

                --primary: #a8a29e;
                --secondary: #7c3aed;
                --accent: #db2777;
                --dark-bg: #131314;
                --card-bg: #1e1f20;
                --text-main: #e2e8f0;
                --text-muted: #94a3b8;
            }
            body {
                background-color: var(--dark-bg);
                color: var(--text-main);
                font-family: 'Outfit', sans-serif;
            }
            .nicegui-content {
                padding: 0;
                margin: 0;
                max-width: 100%;
            }
            .nav-item {
                color: var(--text-muted);
                transition: all 0.3s ease;
                border-radius: 8px;
                padding: 2px 8px;
                text-decoration: none;
            }
            .nav-item:hover, .nav-item.active {
                color: var(--text-main);
                background: rgba(255, 255, 255, 0.1);
            }
            .glass-panel {
                background: rgba(30, 41, 59, 0.7);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        </style>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    """)

    with ui.header().classes('bg-transparent border-b border-white/10 h-12 flex items-center px-4 glass-panel fixed top-0 w-full z-50'):
        ui.icon('smart_toy', size='32px').classes('text-indigo-400 mr-2')
        ui.label('Ollama Manager').classes('text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400')
        
        ui.space()
        
        with ui.row().classes('gap-4 items-center'):
            # Navigation Links
            def nav_link(text, target):
                classes = 'nav-item'
                if target == page_path:
                    classes += ' active'
                ui.link(text, target).classes(classes).style('font-weight: 500')
            
            nav_link('Chat', '/chat')
            # Visual separator using a small vertical line or just margin
            ui.element('div').classes('h-4 w-px bg-white/20 mx-2')
            
            nav_link('Models', '/')
            nav_link('Create', '/create')
            nav_link('Tools', '/tools')
            nav_link('Arena', '/arena')
            nav_link('Batch', '/batch')
            ui.element('div').classes('h-4 w-px bg-white/20 mx-2')
            nav_link('Settings', '/settings')

@ui.page('/')
def index():
    layout('/')
    models.create_page()

@ui.page('/chat')
async def chat_page(model: str = None):
    layout('/chat')
    await chat.create_page(model)

@ui.page('/arena')
async def arena_page():
    layout('/arena')
    await arena.create_page()

@ui.page('/batch')
async def batch_page():
    layout('/batch')
    await batch.create_page()

@ui.page('/tools')
def tools_page():
    layout('/tools')
    tools.create_page()

@ui.page('/create')
def create_new_page(base_model: str = None):
    layout('/create')
    create.create_page(base_model)

@ui.page('/settings')
def settings_page():
    layout('/settings')
    settings.create_page()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Ollama Manager', dark=True, reload=True, port=8080, storage_secret='ollama_manager_secret')
