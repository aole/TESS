from nicegui import ui, app, run
from pages import models, chat, batch, tools, settings, audio, visual, edit, apps, python_page, personas
from services import system_service
from utils.llm_client import client

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
            .toolbar-unload-button {
                min-width: 28px !important;
                width: 28px !important;
                height: 28px !important;
                padding: 0 !important;
                background: transparent !important;
                border: 0 !important;
            }
            .toolbar-unload-button .q-icon {
                font-size: 14px !important;
            }
            .checkerboard-bg {
                background-color: #1f2937;
                background-image: 
                    linear-gradient(45deg, rgba(255,255,255,0.16) 25%, transparent 25%),
                    linear-gradient(-45deg, rgba(255,255,255,0.16) 25%, transparent 25%),
                    linear-gradient(45deg, transparent 75%, rgba(255,255,255,0.16) 75%),
                    linear-gradient(-45deg, transparent 75%, rgba(255,255,255,0.16) 75%);
                background-size: 24px 24px;
                background-position: 0 0, 0 12px, 12px -12px, -12px 0;
            }
            .visual-action-btn {
                min-width: 26px !important;
                width: 26px !important;
                height: 26px !important;
                min-height: unset !important;
                padding: 0 !important;
                background: rgba(0,0,0,0.75) !important;
                color: white !important;
                transition: opacity 0.15s ease !important;
                z-index: 10 !important;
            }
            .visual-grid-cell {
                position: relative;
                overflow: hidden;
                cursor: pointer;
                aspect-ratio: 1 / 1;
                transition: transform 0.15s ease, box-shadow 0.15s ease;
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
            # GPU Indicators
            with ui.row().classes('items-center gap-2'):
                async def unload_loaded_models():
                    unload_button.disable()
                    try:
                        ui.notify('Unloading loaded models...', type='info')
                        success = await client.unload_all_models()
                        if success:
                            ui.notify('Loaded models unloaded', type='positive')
                        else:
                            ui.notify('Failed to unload loaded models', type='negative')
                        await update_gpu_metrics()
                    except RuntimeError as e:
                        if "deleted" not in str(e):
                            raise
                    finally:
                        unload_button.enable()

                unload_button = ui.button(icon='layers_clear', on_click=unload_loaded_models).props('flat dense color=amber-4 size=sm')
                unload_button.classes('toolbar-unload-button')
                unload_button.tooltip('Unload loaded model')

                # VRAM
                with ui.row().classes('items-center gap-2 px-1 py-1') as vram_container:
                    vram_progress = ui.linear_progress(value=0, show_value=False).classes('w-12 h-3 rounded-full bg-white/10').props('color=indigo-400')
                    vram_tooltip = ui.tooltip('VRAM: --')
                
                # Activity
                with ui.row().classes('items-center gap-2 px-1 py-1') as activity_container:
                    activity_progress = ui.linear_progress(value=0, show_value=False).classes('w-12 h-3 rounded-full bg-white/10').props('color=emerald-400')
                    activity_tooltip = ui.tooltip('Activity: --')
                
                async def update_gpu_metrics():
                    try:
                        usage = await run.io_bound(system_service.get_primary_gpu_usage)
                        if usage:
                            # Update VRAM
                            used_gb = usage['used'] / 1024
                            total_gb = usage['total'] / 1024
                            vram_tooltip.set_text(f"VRAM: {used_gb:.1f} / {total_gb:.0f} GB ({usage['vram_percentage']:.1f}%)")
                            vram_progress.set_value(usage['vram_percentage'] / 100)
                            
                            # Update Activity
                            activity_tooltip.set_text(f"GPU Activity: {usage['load']}%")
                            activity_progress.set_value(usage['load'] / 100)
                        else:
                            vram_tooltip.set_text("VRAM: N/A")
                            activity_tooltip.set_text("Activity: N/A")
                    except RuntimeError as e:
                        if "deleted" not in str(e):
                            raise
                
                ui.timer(1.0, update_gpu_metrics)

            ui.element('div').classes('h-4 w-px bg-white/20 mx-2')

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
            nav_link('Python', '/python')
            nav_link('Audio', '/audio')
            nav_link('Visual', '/visual')
            nav_link('Edit', '/edit')
            nav_link('Tools', '/tools')
            nav_link('Batch', '/batch')
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

@ui.page('/batch')
async def batch_page():
    layout('/batch')
    await batch.create_page()

@ui.page('/tools')
def tools_page():
    layout('/tools')
    tools.create_page()


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

@ui.page('/edit')
def edit_page(img: str = None, imgs: str = None):
    layout('/edit')
    edit.create_page(img, imgs)

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
