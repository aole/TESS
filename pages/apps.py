import os
import sys
import importlib.util
from nicegui import ui

def load_app_module(app_path):
    app_name = os.path.basename(app_path)
    main_file = os.path.join(app_path, 'app.py')
    if not os.path.exists(main_file):
        return None
        
    spec = importlib.util.spec_from_file_location(f"apps.{app_name}", main_file)
    if spec is None or spec.loader is None:
        return None
        
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"apps.{app_name}"] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"Error loading app {app_name}: {e}")
        return None

def create_page():
    apps_dir = os.path.join(os.getcwd(), 'apps')
    os.makedirs(apps_dir, exist_ok=True)
    
    # Get all subdirectories in the apps folder, excluding internal ones
    apps_list = [d for d in os.listdir(apps_dir) if os.path.isdir(os.path.join(apps_dir, d)) and d not in ('__pycache__', 'data')]
    
    with ui.row().classes('w-full h-[calc(100vh-3rem)] flex-nowrap m-0 p-0'):
        # Left panel: App list
        with ui.column().classes('w-64 h-full border-r border-white/10 p-4 glass-panel shrink-0'):
            app_container = ui.column().classes('w-full gap-2')
            
        # Right panel: App content
        with ui.column().classes('flex-grow h-full p-6').style('overflow-y: auto;') as content_container:
            ui.label('Select an app from the menu').classes('text-gray-400 m-auto text-lg')
            
        def select_app(app_name):
            content_container.clear()
            app_path = os.path.join(apps_dir, app_name)
            module = load_app_module(app_path)
            
            with content_container:
                if module and hasattr(module, 'render'):
                    try:
                        module.render()
                    except Exception as e:
                        ui.label(f'Error rendering app: {e}').classes('text-red-400')
                else:
                    ui.label(f'App {app_name} is missing a valid app.py with a render() function').classes('text-red-400')
                    
        # Populate app list
        from apps.utils import get_app_badge, register_badge_update_callback
        
        @ui.refreshable
        def render_app_list():
            for app_name in apps_list:
                display_name = app_name.replace('_', ' ').title()
                badge_count = get_app_badge(app_name)
                
                with ui.button(on_click=lambda a=app_name: select_app(a)).classes('w-full justify-start relative px-4 py-2').props('no-caps flat'):
                    ui.label(display_name)
                    if badge_count and int(badge_count) > 0:
                        ui.badge(str(badge_count), color='red').classes('absolute right-2 top-1/2 -translate-y-1/2')
                        
        with app_container:
            render_app_list()
            
        # Refresh badges in real-time when updated
        register_badge_update_callback(render_app_list.refresh)

        # Load default app
        if 'custom_app_tutorial' in apps_list:
            select_app('custom_app_tutorial')
        elif apps_list:
            select_app(apps_list[0])
