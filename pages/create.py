from nicegui import ui
from utils.llm_client import client
import asyncio
from typing import Optional

def create_page(base_model: str = None):
    # State
    model_options = []
    selected_model = base_model
    new_model_name = ""
    
    # UI Elements references
    model_select: Optional[ui.select] = None
    system_area: Optional[ui.textarea] = None
    template_area: Optional[ui.textarea] = None
    params_area: Optional[ui.textarea] = None
    name_input: Optional[ui.input] = None
    status_label: Optional[ui.label] = None

    async def get_template():
        if not selected_model:
            ui.notify("Please select a base model first", type='warning')
            return
            
        try:
            info = await client.show_model(selected_model)
            
            # Extract components
            if template_area:
                template_area.value = info.get('template', '')
            if system_area:
                system_area.value = info.get('system', '')
            if params_area:
                # Convert params text to something editable or keep as text
                # formatting as "key value" lines for simplicity if it comes as string
                # info['parameters'] usually comes as a single string with newlines from `show`
                params_area.value = info.get('parameters', '')
                
            ui.notify(f"Components loaded from {selected_model}", type='success')
        except Exception as e:
            ui.notify(f"Error loading info: {e}", type='negative')

    async def refresh_models():
        nonlocal model_options
        try:
            models = await client.list_models()
            model_options = [m['model'] for m in models]
            if model_select:
                model_select.options = model_options
                model_select.update()
                
            if selected_model and selected_model in model_options:
                model_select.value = selected_model
                await get_template()
                
        except Exception as e:
            ui.notify(f"Error loading models: {e}", type='negative')



    async def create_new_model():
        nonlocal new_model_name
        
        name = name_input.value.strip() if name_input else ""
        system = system_area.value if system_area else ""
        template = template_area.value if template_area else ""
        params_text = params_area.value if params_area else ""
        
        if not name:
            ui.notify("Please enter a new model name", type='warning')
            return
        
        # Parse parameters from text to dict
        parameters = {}
        if params_text:
            try:
                for line in params_text.split('\n'):
                    parts = line.strip().split()
                    
                    # Optional: strip leading PARAMETER keyword common in Modelfiles
                    if parts and parts[0].upper() == 'PARAMETER':
                        parts = parts[1:]

                    if len(parts) >= 2:
                        key = parts[0]
                        # Handling potential types if needed, but strings usually work for create
                        # or simple parsing
                        val = " ".join(parts[1:])
                        # Try to convert to numbers if possible
                        try:
                            if '.' in val:
                                val = float(val)
                            else:
                                val = int(val)
                        except:
                            pass
                        if key in parameters:
                            if isinstance(parameters[key], list):
                                parameters[key].append(val)
                            else:
                                parameters[key] = [parameters[key], val]
                        else:
                            parameters[key] = val
            except Exception as e:
                ui.notify(f"Error parsing parameters: {e}", type='warning')
                return

        ui.notify(f"Creating model {name}...", type='info')
        
        try:
            async for progress in client.create_model(
                model=name, 
                from_=selected_model,
                system=system,
                template=template,
                parameters=parameters
            ):
                if 'status' in progress:
                    if status_label:
                        status_label.text = progress['status']
                if 'error' in progress:
                    ui.notify(f"Error: {progress['error']}", type='negative')
                    return

            ui.notify(f"Model {name} created successfully", type='success')
            ui.navigate.to('/')
        except Exception as e:
            ui.notify(f"Failed to create model: {e}", type='negative')

    # Layout
    with ui.column().classes('w-full h-full pt-14 px-4 max-w-7xl mx-auto'):
        ui.label('Create New Model').classes('text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-400 mb-6')

        with ui.grid(columns=2).classes('w-full gap-6'):
            # Left Column: Selection & Configuration
            with ui.column().classes('gap-4'):
                with ui.card().classes('w-full glass-panel p-4'):
                    ui.label('1. Select Base Model').classes('text-lg font-bold text-indigo-400 mb-2')
                    def set_model(e): 
                        nonlocal selected_model
                        selected_model = e.value
                        if name_input:
                            name_input.value = selected_model

                    model_select = ui.select(
                        options=[], 
                        label='Base Model',
                        on_change=set_model
                    ).classes('w-full')

                    ui.button('Get Template', on_click=get_template).props('icon=download color=secondary').classes('w-full mt-2')

                with ui.card().classes('w-full glass-panel p-4'):
                    ui.label('3. Name & Create').classes('text-lg font-bold text-indigo-400 mb-2')
                    name_input = ui.input('New Model Name', placeholder='custom-model').classes('w-full')
                    ui.button('Create Model', on_click=create_new_model).props('icon=add_circle color=primary').classes('w-full mt-4')
                    status_label = ui.label('').classes('text-sm text-muted mt-2')

            # Right Column: Template & Details
            with ui.card().classes('w-full glass-panel p-4 h-full'):
                with ui.tabs().classes('w-full') as tabs:
                    tab_sys = ui.tab('System')
                    tab_tmpl = ui.tab('Template')
                    tab_params = ui.tab('Parameters')
                
                with ui.tab_panels(tabs, value=tab_sys).classes('w-full h-full bg-transparent'):
                    with ui.tab_panel(tab_sys):
                        system_area = ui.textarea(placeholder='You are a helpful assistant...').classes('w-full h-full font-mono text-sm').props('autogrow input-class=h-full')
                    
                    with ui.tab_panel(tab_tmpl):
                        template_area = ui.textarea(placeholder='{{ .System }} ...').classes('w-full h-full font-mono text-sm').props('autogrow input-class=h-full')
                        
                    with ui.tab_panel(tab_params):
                        params_area = ui.textarea(placeholder='temperature 0.7\nstop "User:"').classes('w-full h-full font-mono text-sm').props('autogrow input-class=h-full')


    # Initial load
    ui.timer(0.1, refresh_models, once=True)
