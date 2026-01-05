from nicegui import ui
from services.tool_service import tool_service, Tool
from utils.ollama_client import client
import asyncio

def create_page():
    # Helper to refresh the list
    def refresh_list():
        tools = tool_service.get_all_tools()
        table.rows = [t.to_dict() for t in tools]
        table.update()

    # Create/Edit Dialog
    async def open_tool_dialog(tool: Tool = None):
        is_edit = tool is not None
        dialog_title = 'Edit Tool' if is_edit else 'Create Tool'
        
        # Initial values
        name_val = tool.name if is_edit else ''
        desc_val = tool.description if is_edit else ''
        code_val = tool.code if is_edit else 'def my_tool():\n    pass'
        
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
            ui.label(dialog_title).classes('text-lg font-bold')
            
            with ui.row().classes('w-full gap-4'):
                name_input = ui.input('Name', value=name_val).classes('flex-grow')
                if is_edit:
                    name_input.disable() # Don't allow renaming for simplicity in this version
                
                desc_input = ui.input('Description', value=desc_val).classes('flex-grow')

            ui.label('Python Code').classes('mt-2 text-sm text-muted')
            code_editor = ui.codemirror(value=code_val, language='python').classes('h-64 border rounded')

            # LLM Docs Generation
            async def generate_docs():
                current_code = code_editor.value
                if not current_code: return
                
                # Get available models
                try:
                    models = await client.list_models()
                    if not models:
                        ui.notify('No Ollama models found', type='warning')
                        return
                    model_name = models[0]['model'] # Default to first
                    
                    ui.notify(f'Generating docs using {model_name}...', type='info')
                    
                    prompt = f"Add docstrings and type hints to the following Python code. Return ONLY the python code with improvements, no markdown formatting or backticks:\n\n{current_code}"
                    
                    response_text = ""
                    gen = await client.generate(model=model_name, prompt=prompt)
                    async for chunk in gen:
                        response_text += chunk.get('response', '')
                    
                    # Clean up if model added markdown blocks despite instructions
                    cleaned_code = response_text.strip()
                    if cleaned_code.startswith('```python'):
                        cleaned_code = cleaned_code[9:]
                    if cleaned_code.startswith('```'):
                        cleaned_code = cleaned_code[3:]
                    if cleaned_code.endswith('```'):
                        cleaned_code = cleaned_code[:-3]
                        
                    code_editor.value = cleaned_code.strip()
                    ui.notify('Docs generated!', type='success')
                    
                except Exception as e:
                    ui.notify(f'Generation failed: {e}', type='negative')

            with ui.row().classes('w-full justify-between items-center mt-2'):
                ui.button('Generate Docs with AI', on_click=generate_docs, icon='auto_awesome').props('flat color=secondary')

            async def save():
                if not name_input.value:
                    ui.notify('Name is required', type='warning')
                    return
                
                new_tool = Tool(
                    name=name_input.value,
                    description=desc_input.value,
                    code=code_editor.value,
                    active=True if not is_edit else tool.active
                )
                
                success = False
                if is_edit:
                    success = tool_service.update_tool(tool.name, new_tool)
                else:
                    success = tool_service.create_tool(new_tool)
                
                if success:
                    ui.notify('Tool saved', type='success')
                    refresh_list()
                    dialog.close()
                else:
                    ui.notify('Error saving tool (check if name exists)', type='negative')

            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=save).props('color=primary')
                
        dialog.open()

    # Delete Action
    async def delete_tool_action(row):
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Delete {row['name']}?").classes('font-bold')
            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=lambda: dialog.submit(False)).props('flat')
                ui.button('Delete', on_click=lambda: dialog.submit(True)).props('color=negative')
        
        if await dialog:
            if tool_service.delete_tool(row['name']):
                ui.notify(f"Deleted {row['name']}", type='success')
                refresh_list()
            else:
                ui.notify("Delete failed", type='negative')

    # Toggle Active Action
    def toggle_active_action(row):
        if tool_service.toggle_tool_active(row['name']):
            refresh_list()

    # Layout
    with ui.column().classes('w-full h-full pt-14 px-4 max-w-7xl mx-auto'):
        # Header
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('Tools').classes('text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-pink-400 to-orange-400')
            ui.button('Create Tool', on_click=lambda: open_tool_dialog(None), icon='add').props('color=secondary')

        # Table
        columns = [
            {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True, 'classes': 'font-bold text-indigo-300'},
            {'name': 'description', 'label': 'Description', 'field': 'description', 'align': 'left'},
            {'name': 'active', 'label': 'Active', 'field': 'active', 'align': 'center'},
            {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
        ]

        table = ui.table(columns=columns, rows=[], row_key='name').classes('w-full glass-panel remove-defaults')
        
        # Slots
        table.add_slot('body-cell-active', r'''
            <q-td key="active" :props="props">
                <q-icon :name="props.row.active ? 'check_circle' : 'cancel'" 
                        :class="props.row.active ? 'text-green-400' : 'text-red-400'" size="sm" />
            </q-td>
        ''')

        table.add_slot('body-cell-actions', r'''
            <q-td key="actions" :props="props" class="flex gap-2 justify-end">
                <q-btn flat round color="secondary" icon="power_settings_new" size="sm" @click="$parent.$emit('toggle', props.row)" >
                    <q-tooltip>Toggle Active</q-tooltip>
                </q-btn>
                <q-btn flat round color="warning" icon="edit" size="sm" @click="$parent.$emit('edit', props.row)" />
                <q-btn flat round color="negative" icon="delete" size="sm" @click="$parent.$emit('delete', props.row)" />
            </q-td>
        ''')

        # Events
        table.on('toggle', lambda e: toggle_active_action(e.args))
        table.on('edit', lambda e: open_tool_dialog(Tool.from_dict(e.args)))
        table.on('delete', lambda e: delete_tool_action(e.args))

        # Initial Load
        refresh_list()
