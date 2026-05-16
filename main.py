from nicegui import ui, app, run
from pages import models, chat, arena, batch, tools, create, settings, google, playground, audio, visual, apps, python_page, personas
from services import system_service

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
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    """)

    with ui.header().classes('bg-transparent border-b border-white/10 h-12 flex items-center px-4 glass-panel fixed top-0 w-full z-50'):
        ui.icon('smart_toy', size='32px').classes('text-indigo-400 mr-2')
        ui.label('TESS').classes('text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400').tooltip('Text Evaluation & Synthesis System')
        
        ui.space()
        
        with ui.row().classes('gap-4 items-center'):
            # VRAM Indicator
            with ui.row().classes('items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10') as vram_container:
                vram_icon = ui.icon('memory', size='16px').classes('text-indigo-400')
                vram_progress = ui.linear_progress(value=0, show_value=False).classes('w-12 h-1 rounded-full bg-white/10').props('color=indigo-400')
                vram_tooltip = ui.tooltip('VRAM: --')
                
                async def update_vram():
                    usage = await run.io_bound(system_service.get_primary_gpu_usage)
                    if usage:
                        used_gb = usage['used'] / 1024
                        total_gb = usage['total'] / 1024
                        vram_tooltip.set_text(f"VRAM: {used_gb:.1f} / {total_gb:.0f} GB ({usage['percentage']:.1f}%)")
                        vram_progress.set_value(usage['percentage'] / 100)
                        
                        # Change color based on usage
                        if usage['percentage'] > 90:
                            vram_progress.props('color=red-500')
                            vram_icon.classes('text-red-400', remove='text-indigo-400 text-orange-400')
                        elif usage['percentage'] > 75:
                            vram_progress.props('color=orange-500')
                            vram_icon.classes('text-orange-400', remove='text-indigo-400 text-red-400')
                        else:
                            vram_progress.props('color=indigo-500')
                            vram_icon.classes('text-indigo-400', remove='text-red-400 text-orange-400')
                    else:
                        vram_tooltip.set_text("VRAM: N/A")
                
                ui.timer(1.0, update_vram)
                # We don't call update_vram() here because it might block the initial page load if nvidia-smi is slow.
                # The timer will handle the first update shortly.

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
            nav_link('Personas', '/personas')
            nav_link('Create', '/create')
            nav_link('Playground', '/playground')
            nav_link('Python', '/python')
            nav_link('Audio', '/audio')
            nav_link('Visual', '/visual')
            nav_link('Tools', '/tools')
            nav_link('Arena', '/arena')
            nav_link('Batch', '/batch')
            nav_link('Google', '/google')
            nav_link('Apps', '/apps')
            ui.element('div').classes('h-4 w-px bg-white/20 mx-2')
            nav_link('Settings', '/settings')

@ui.page('/')
def index():
    layout('/')
    models.create_page()

@ui.page('/chat')
async def chat_page(model: str = None, new_chat: bool = False):
    layout('/chat')
    await chat.create_page(model, new_chat)

@ui.page('/arena')
async def arena_page():
    layout('/arena')
    await arena.create_page()

@ui.page('/batch')
async def batch_page():
    layout('/batch')
    await batch.create_page()


@ui.page('/google')
def google_page():
    layout('/google')
    google.create_page()

@ui.page('/tools')
def tools_page():
    layout('/tools')
    tools.create_page()

@ui.page('/create')
def create_new_page(base_model: str = None):
    layout('/create')
    create.create_page(base_model)

@ui.page('/playground')
def playground_page():
    layout('/playground')
    playground.create_page()

@ui.page('/python')
def python_ide_page():
    layout('/python')
    python_page.create_page()

@ui.page('/audio')
def audio_page():
    layout('/audio')
    audio.create_page()

@ui.page('/visual')
def visual_page():
    layout('/visual')
    visual.create_page()

@ui.page('/settings')
def settings_page():
    layout('/settings')
    settings.create_page()

@ui.page('/apps')
@ui.page('/apps/{app_name}')
def apps_route(app_name: str = None):
    layout('/apps')
    apps.create_page(app_name)

@ui.page('/personas')
def personas_page():
    layout('/personas')
    personas.create_page()

if __name__ in {"__main__", "__mp_main__"}:
    app.add_static_files('/data', 'data')
    app.add_static_files('/output', '.')
    ui.run(
        title='TESS',
        dark=True,
        reload=True,
        port=8080,
        storage_secret='ollama_manager_secret',
        uvicorn_reload_excludes='.*, .py[cod], .sw.*, ~*, data/tools/*, data/python/*, data/personas.json',
    )
