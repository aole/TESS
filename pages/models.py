from typing import Callable, Optional
from nicegui import app, ui
from utils.llm_client import client
from services.rating_service import rating_service
from services.persona_service import persona_service, NO_PERSONA_ID
import asyncio
from dataclasses import dataclass

import inspect

def supports_tools(model_name: str, family: str) -> bool:
    model_name_lower = model_name.lower()
    
    # Check dynamic blacklist from app.storage.general
    try:
        models_without = app.storage.general.get('models_without_tools', [])
        # Extract base names (without tags) for comparison
        model_base = model_name_lower.split(':')[0]
        if any(m.lower() == model_name_lower or m.lower().split(':')[0] == model_base for m in models_without):
            return False
    except Exception:
        pass

    return True



@dataclass
class PullState:
    is_pulling: bool = False
    model_name: str = ""
    status_text: str = ""
    progress: float = 0.0
    progress_text: str = "0%"

# Global state to persist across refreshes
pull_state = PullState()
current_pull_task: Optional[asyncio.Task] = None

async def pull_model_task(model_name: str, on_complete: Optional[Callable] = None):
    pull_state.is_pulling = True
    pull_state.model_name = model_name
    pull_state.progress = 0.0
    pull_state.progress_text = "0%"
    pull_state.status_text = f"Starting pull for {model_name}..."
    
    try:
        async for progress_update in client.pull_model(model_name):
            status = progress_update.get('status', '')
            pull_state.status_text = f"{status}"
            
            # Calculate progress if available
            total = progress_update.get('total')
            completed = progress_update.get('completed')
            if total and completed:
                pull_state.progress = completed / total
                pull_state.progress_text = f"{int(pull_state.progress * 100)}%"
            elif status == 'success':
                pull_state.progress = 1.0
                pull_state.progress_text = "100%"
        
        # Wait a moment to ensure Ollama registers the new model and user sees 100%
        await asyncio.sleep(1.0)
                
    except Exception as e:
        pull_state.status_text = f"Error: {e}"
        # Wait a bit so user sees the error
        await asyncio.sleep(3)
    finally:
        pull_state.is_pulling = False
        pull_state.progress = 0.0 
        pull_state.progress_text = "0%" 
        if on_complete:
            if inspect.iscoroutinefunction(on_complete):
                await on_complete()
            else:
                on_complete() 

def create_page():
    # Helper to refresh the list
    async def refresh_list():
        try:
            models = await client.list_models()
        except Exception as e:
            ui.notify(f"Error loading models: {e}", type='negative')
            models = []
            
        # Format size
        for m in models:
            size_gb = m.get('size', 0) / (1024**3)
            m['size_str'] = f"{size_gb:.2f} GB"
            # Truncate digest
            m['digest_short'] = m.get('digest', '')[:12] + '...'
            m['family_str'] = m.get('details', {}).get('family', 'N/A')
            
            # Tool support check
            m['supports_tools'] = supports_tools(m['model'], m['family_str'])
            m['tools_support_str'] = "Supported" if m['supports_tools'] else "Not Supported"
            
            # Rating Stats
            best = rating_service.get_best_tag_for_model(m['model'])
            if best:
                m['rating_str'] = f"{best['tag']}: {best['average']}★"
            else:
                m['rating_str'] = "-"
            
        table.rows = models
        table.update()

    # Helper to show details
    async def show_details(model_name):
        details_content.clear()
        with details_content:
            ui.spinner('dots').classes('self-center')
        details_container.set_visibility(True)
        
        # Fetch details
        info = await client.show_model(model_name)
        
        details_content.clear()
        with details_content:
            with ui.row().classes('w-full justify-between items-start'):
                ui.label(f"Details: {model_name}").classes('text-xl font-bold text-indigo-400')
                ui.button(icon='close', on_click=lambda: details_container.set_visibility(False)).props('flat round dense')
            
            if info:
                # Basic Info Grid
                with ui.grid(columns=2).classes('w-full gap-4 mt-4'):
                    with ui.column().classes('p-4 glass-panel rounded'):
                        ui.label('Format').classes('text-xs text-muted')
                        ui.label(info.get('details', {}).get('format', 'N/A'))
                    
                    with ui.column().classes('p-4 glass-panel rounded'):
                        ui.label('Family').classes('text-xs text-muted')
                        ui.label(info.get('details', {}).get('family', 'N/A'))
                    
                    with ui.column().classes('p-4 glass-panel rounded'):
                        ui.label('Parameter Size').classes('text-xs text-muted')
                        ui.label(info.get('details', {}).get('parameter_size', 'N/A'))
                        
                    with ui.column().classes('p-4 glass-panel rounded'):
                        ui.label('Quantization').classes('text-xs text-muted')
                        ui.label(info.get('details', {}).get('quantization_level', 'N/A'))

                # System Prompt / Modelfile
                if 'modelfile' in info:
                    ui.label('Modelfile').classes('text-lg font-bold mt-6 mb-2 text-indigo-400')
                    ui.code(info['modelfile']).classes('w-full rounded bg-transparent border border-white/10')
                
                if info.get('license'):
                     with ui.expansion('License').classes('w-full mt-4'):
                         ui.markdown(info['license'])

        
    # Actions
    async def delete_model(model):
        with ui.dialog() as dialog, ui.card():
            ui.label(f'Are you sure you want to delete {model}?').classes('font-bold')
            with ui.row().classes('w-full justify-end'):
                ui.button('Cancel', on_click=lambda: dialog.submit(False)).props('flat')
                ui.button('Delete', on_click=lambda: dialog.submit(True)).props('color=negative')
        
        if await dialog:
            if await client.delete_model(model):
                ui.notify(f'Deleted {model}', type='success')
                await refresh_list()
            else:
                ui.notify(f'Failed to delete {model}', type='negative')

    async def cancel_pull():
        global current_pull_task
        if current_pull_task and not current_pull_task.done():
            current_pull_task.cancel()
            try:
                await current_pull_task
            except asyncio.CancelledError:
                pass
            ui.notify('Download cancelled', type='warning')


    async def rename_model_dialog(model):
        with ui.dialog() as dialog, ui.card():
            ui.label(f'Rename {model}').classes('text-lg font-bold')
            new_name = ui.input('New Name', value=model).classes('w-full')
            
            async def do_rename():
                if not new_name.value: return
                if await client.copy_model(model, new_name.value) and await client.delete_model(model):
                    ui.notify(f'Renamed to {new_name.value}', type='success')
                    await refresh_list()
                    dialog.close()
                else:
                    ui.notify('Rename failed', type='negative')
            
            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Rename', on_click=do_rename).props('color=primary')
        dialog.open()

    async def start_pull_model():
        raw_input = pull_input.value
        if not raw_input: return
        
        # Clean input: remove common command prefixes if pasted
        model_name = raw_input.strip()
        if model_name.startswith('ollama run '):
            model_name = model_name[11:].strip()
        elif model_name.startswith('ollama pull '):
            model_name = model_name[12:].strip()
            
        if pull_state.is_pulling:
            ui.notify("Already pulling a model. Please wait.", type='warning')
            return
            
        pull_input.value = ''
        ui.notify(f'Pulling {model_name}...', type='info')
        
        # Start background task
        global current_pull_task
        current_pull_task = asyncio.create_task(pull_model_task(model_name, on_complete=refresh_list))

    def configure_model_dialog(model_name: str, family_str: str):
        # Fetch current custom configuration if it exists synchronously
        model_configs = app.storage.general.get('model_configurations', {})
        model_cfg = model_configs.get(model_name, {})

        # Use standard settings as fallback while loading
        saved_temp = model_cfg.get('temperature', 0.7)
        saved_top_p = model_cfg.get('top_p', 0.9)
        saved_repeat_penalty = model_cfg.get('repeat_penalty', 1.1)
        saved_sys = model_cfg.get('system_prompt', '')
        saved_persona = model_cfg.get('persona_id', NO_PERSONA_ID)
        saved_tools = model_cfg.get('tools_enabled', supports_tools(model_name, family_str))
        saved_memory = model_cfg.get('memory_enabled', True)

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6 bg-[#18181b] border border-white/10 text-gray-200 rounded-xl shadow-2xl'):
            # Header with loading spinner
            with ui.row().classes('w-full justify-between items-center mb-1'):
                with ui.column().classes('gap-0'):
                    ui.label(f'Configure Model').classes('text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-400')
                    ui.label(model_name).classes('text-sm font-mono text-indigo-300')
                loading_spinner = ui.spinner('dots', size='md', color='indigo').tooltip('Loading defaults from model file...')
                loading_spinner.set_visibility(False)

            # Persona dropdown
            ui.label('Default Persona').classes('text-sm font-medium text-gray-400 mb-1')
            persona_opts = {p['id']: p['name'] for p in persona_service.get_all_persona_options()}
            
            def on_persona_change(e):
                pid = e.value
                if pid != NO_PERSONA_ID:
                    persona = persona_service.get_persona(pid)
                    if persona:
                        sys_prompt_input.value = persona['system_prompt']
            
            persona_select = ui.select(
                options=persona_opts,
                value=saved_persona,
                on_change=on_persona_change
            ).props('dense options-dense outlined dark').classes('w-full text-sm mb-4')

            # System Prompt
            ui.label('Default System Message / Persona Prompt').classes('text-sm font-medium text-gray-400 mb-1')
            sys_prompt_input = ui.textarea(
                placeholder='You are a helpful assistant...',
                value=saved_sys
            ).props('dense rows=3 filled flat').classes('w-full text-sm mb-4 bg-white/5 rounded-md text-gray-200')

            # Sliders for parameters
            with ui.expansion('Model Parameters', icon='tune', value=True).classes('w-full bg-white/5 rounded-lg mb-4').props('dense'):
                with ui.column().classes('w-full p-4 gap-4'):
                    # Temperature
                    with ui.column().classes('w-full gap-1'):
                        with ui.row().classes('w-full justify-between'):
                            ui.label('Temperature').classes('text-xs text-gray-400')
                            temp_val = ui.label().classes('text-xs text-indigo-400 font-mono')
                        temp_slider = ui.slider(min=0.0, max=1.0, step=0.1, value=saved_temp).props('label-always thumb-path=""')
                        temp_val.bind_text_from(temp_slider, 'value', backward=lambda v: f"{v:.1f}")

                    # Top P
                    with ui.column().classes('w-full gap-1'):
                        with ui.row().classes('w-full justify-between'):
                            ui.label('Top P').classes('text-xs text-gray-400')
                            top_p_val = ui.label().classes('text-xs text-indigo-400 font-mono')
                        top_p_slider = ui.slider(min=0.0, max=1.0, step=0.1, value=saved_top_p).props('label-always')
                        top_p_val.bind_text_from(top_p_slider, 'value', backward=lambda v: f"{v:.1f}")

                    # Repeat Penalty
                    with ui.column().classes('w-full gap-1'):
                        with ui.row().classes('w-full justify-between'):
                            ui.label('Repeat Penalty').classes('text-xs text-gray-400')
                            rep_val = ui.label().classes('text-xs text-indigo-400 font-mono')
                        repeat_penalty_slider = ui.slider(min=0.0, max=2.0, step=0.1, value=saved_repeat_penalty).props('label-always')
                        rep_val.bind_text_from(repeat_penalty_slider, 'value', backward=lambda v: f"{v:.1f}")

            # Checkboxes
            with ui.row().classes('w-full gap-6 mb-6'):
                tools_checkbox = ui.checkbox('Can use Tools', value=saved_tools).classes('text-sm text-gray-300')
                memory_checkbox = ui.checkbox('Can use Memory', value=saved_memory).classes('text-sm text-gray-300')

            # Buttons
            async def do_save():
                # Store configurations in app.storage.general
                if 'model_configurations' not in app.storage.general:
                    app.storage.general['model_configurations'] = {}
                
                app.storage.general['model_configurations'][model_name] = {
                    'temperature': temp_slider.value,
                    'top_p': top_p_slider.value,
                    'repeat_penalty': repeat_penalty_slider.value,
                    'system_prompt': sys_prompt_input.value,
                    'persona_id': persona_select.value,
                    'tools_enabled': tools_checkbox.value,
                    'memory_enabled': memory_checkbox.value
                }
                
                # Also synchronize the tools support list
                if 'models_without_tools' not in app.storage.general:
                    app.storage.general['models_without_tools'] = []
                
                if not tools_checkbox.value:
                    if model_name not in app.storage.general['models_without_tools']:
                        app.storage.general['models_without_tools'].append(model_name)
                else:
                    if model_name in app.storage.general['models_without_tools']:
                        app.storage.general['models_without_tools'].remove(model_name)
                
                ui.notify(f"Configuration saved for {model_name}", type='positive')
                dialog.close()
                ui.navigate.to(f'/chat?model={model_name}&new_chat=true')

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat color=grey').classes('text-sm')
                ui.button('Save', on_click=do_save).props('color=primary').classes('text-sm font-bold px-4')
                
        dialog.open()

        # Fetch defaults from model file asynchronously IF we do not have a custom saved configuration yet
        if not model_cfg:
            async def load_defaults():
                try:
                    loading_spinner.set_visibility(True)
                    defaults = await client.get_model_parameters(model_name)
                    
                    temp_slider.value = defaults.get('temperature', 0.7)
                    top_p_slider.value = defaults.get('top_p', 0.9)
                    repeat_penalty_slider.value = defaults.get('repeat_penalty', 1.1)
                    sys_prompt_input.value = defaults.get('system', '')
                except Exception:
                    pass
                finally:
                    loading_spinner.set_visibility(False)
            
            asyncio.create_task(load_defaults())

    # Layout
    with ui.column().classes('w-full h-full pt-14 px-4 max-w-7xl mx-auto'):
        # Header + Pull
        with ui.row().classes('w-full justify-between items-center mb-2 gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.label('Models').classes('text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-400')
                ui.button(on_click=refresh_list, icon='refresh').props('flat round color=white')
            
            with ui.row().classes('items-center gap-2'):
                pull_input = ui.input(placeholder='ollama run user/model').classes('w-64 glass-panel px-2 rounded')
                ui.button('Pull', on_click=start_pull_model).props('color=secondary icon=cloud_download')

        # Progress Area
        pull_container = ui.card().classes('w-full mb-4 glass-panel bg-indigo-500/10 p-2').bind_visibility_from(pull_state, 'is_pulling')
        with pull_container:
             with ui.row().classes('w-full items-center gap-4'):
                 ui.spinner('dots').classes('text-indigo-400')
                 with ui.column().classes('flex-grow'):
                     with ui.row().classes('w-full justify-between items-center'):
                         ui.label().bind_text_from(pull_state, 'status_text').classes('text-sm font-mono text-indigo-300')
                         ui.label().bind_text_from(pull_state, 'progress_text').classes('text-sm font-mono font-bold text-teal-400')
                     ui.linear_progress(show_value=False).bind_value_from(pull_state, 'progress').classes('w-full')
                 ui.button(icon='cancel', on_click=cancel_pull).props('flat round color=negative dense')

        # Model Table
        columns = [
            {'name': 'name', 'label': 'Name (Click to Chat)', 'field': 'model', 'align': 'left', 'sortable': True, 'classes': 'text-indigo-300 font-mono font-bold'},
            {'name': 'size', 'label': 'Size', 'field': 'size_str', 'align': 'left', 'sortable': True},
            {'name': 'family', 'label': 'Family', 'field': 'family_str', 'align': 'left', 'sortable': True},
            {'name': 'tools', 'label': 'Tools', 'field': 'tools_support_str', 'align': 'left', 'sortable': True},
            {'name': 'rating', 'label': 'Best Rating', 'field': 'rating_str', 'align': 'left', 'sortable': True, 'classes': 'text-yellow-400 font-bold'},
            {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
        ]
        
        table = ui.table(columns=columns, rows=[], row_key='model').classes('w-full glass-panel remove-defaults')
        table.add_slot('body-cell-name', r'''
            <q-td key="name" :props="props">
                <div class="cursor-pointer text-indigo-300 font-mono font-bold hover:text-indigo-100 flex items-center gap-2 group" @click="$parent.$emit('chat', props.row)">
                     {{ props.row.model }}
                     <q-icon name="chat" size="xs" class="opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
            </q-td>
        ''')
        table.add_slot('body-cell-tools', r'''
            <q-td key="tools" :props="props">
                <div class="flex items-center">
                    <span v-if="!props.row.supports_tools" class="text-red-400/90 hover:text-red-300 flex items-center cursor-help">
                        <q-icon name="block" size="sm" class="mr-1" />
                        <q-tooltip class="bg-[#18181b] text-gray-200 border border-white/10 text-xs rounded p-2">This model does not support tools / function calling</q-tooltip>
                    </span>
                    <span v-else class="text-teal-400/80 flex items-center">
                        <q-icon name="check" size="xs" class="mr-1" />
                        <q-tooltip class="bg-[#18181b] text-gray-200 border border-white/10 text-xs rounded p-2">This model supports tools / function calling</q-tooltip>
                    </span>
                </div>
            </q-td>
        ''')

        table.add_slot('body-cell-actions', r'''
            <q-td key="actions" :props="props" class="flex gap-2 justify-end">
                <q-btn flat round color="white" icon="info" size="sm" @click="$parent.$emit('details', props.row)" />
                <q-btn flat round color="secondary" icon="content_copy" size="sm" @click="$parent.$emit('create', props.row)" />
                <q-btn flat round color="warning" icon="edit" size="sm" @click="$parent.$emit('rename', props.row)" />
                <q-btn flat round color="negative" icon="delete" size="sm" @click="$parent.$emit('delete', props.row)" />
            </q-td>
        ''')
        


        # Event binding for slot buttons
        table.on('details', lambda e: show_details(e.args['model']))
        table.on('chat', lambda e: configure_model_dialog(e.args['model'], e.args.get('family_str', 'N/A')))
        table.on('create', lambda e: ui.navigate.to(f'/create?base_model={e.args["model"]}'))
        table.on('rename', lambda e: rename_model_dialog(e.args['model']))
        table.on('delete', lambda e: delete_model(e.args['model']))


        # Details Panel
        details_container = ui.card().classes('w-full mt-2 glass-panel animate-fade-in p-2')
        details_container.set_visibility(False)
        with details_container:
            details_content = ui.column().classes('w-full gap-2')

        # Initial Load
        ui.timer(0.1, refresh_list, once=True)
