from nicegui import ui
from services.tool_service import tool_service, Tool
from utils.llm_client import client
import asyncio

def create_page():
    # ── State ────────────────────────────────────────────────────────────────
    state = {
        'selected_tool': None,   # Tool object currently loaded in the panel
        'is_new': False,         # True when creating a new tool
    }

    # ── Refs (filled after UI is built) ─────────────────────────────────────
    refs = {}

    # ── Helpers ──────────────────────────────────────────────────────────────
    def refresh_list():
        tools = tool_service.get_all_tools()
        table.rows = [t.to_dict() for t in tools]
        table.update()

    def _set_panel_readonly(readonly: bool):
        """Enable / disable the editable fields in the right panel."""
        if readonly:
            refs['name_input'].disable()
            refs['code_editor'].props('read-only')
            refs['gen_docs_btn'].disable()
            refs['save_btn'].disable()
        else:
            refs['name_input'].enable()
            refs['code_editor'].props(remove='read-only')
            refs['gen_docs_btn'].enable()
            refs['save_btn'].enable()

    def load_tool_into_panel(tool: Tool | None, is_new: bool = False):
        """Populate the right panel with the given tool (or empty for new)."""
        state['selected_tool'] = tool
        state['is_new'] = is_new

        if tool is None and not is_new:
            # Nothing selected — show placeholder state
            refs['panel_title'].set_text('No tool selected')
            refs['name_input'].value = ''
            refs['desc_input'].value = ''
            refs['code_editor'].value = ''
            refs['name_input'].disable()
            refs['code_editor'].props('read-only')
            refs['gen_docs_btn'].disable()
            refs['save_btn'].disable()
            refs['panel_hint'].set_text('Select a tool from the list or create a new one.')
            refs['panel_hint'].set_visibility(True)
            return

        refs['panel_hint'].set_visibility(False)

        if is_new:
            refs['panel_title'].set_text('Create Tool')
            refs['name_input'].value = ''
            refs['desc_input'].value = ''
            refs['code_editor'].value = 'def my_tool():\n    pass'
            refs['name_input'].enable()
            refs['code_editor'].props(remove='read-only')
            refs['gen_docs_btn'].enable()
            refs['save_btn'].enable()
        else:
            refs['panel_title'].set_text(f'Edit — {tool.name}')
            refs['name_input'].value = tool.name
            refs['desc_input'].value = tool.description or ''
            refs['code_editor'].value = tool.code or ''
            # Builtin tools are read-only
            _set_panel_readonly(tool.is_builtin)
            if not tool.is_builtin:
                refs['name_input'].disable()  # Don't allow renaming

    # ── AI Docs Generation ───────────────────────────────────────────────────
    async def generate_docs():
        current_code = refs['code_editor'].value
        if not current_code:
            return
        try:
            models = await client.list_models()
            if not models:
                ui.notify('No Ollama models found', type='warning')
                return
            model_name = models[0]['model']
            ui.notify(f'Generating docs using {model_name}…', type='info')
            prompt = (
                "Add docstrings and type hints to the following Python code. "
                "Return ONLY the python code with improvements, no markdown formatting or backticks:\n\n"
                + current_code
            )
            response_text = ''
            gen = await client.generate(model=model_name, prompt=prompt)
            async for chunk in gen:
                response_text += chunk.get('response', '')
            cleaned = response_text.strip()
            for prefix in ('```python', '```'):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            refs['code_editor'].value = cleaned.strip()
            ui.notify('Docs generated!', type='success')
        except Exception as e:
            ui.notify(f'Generation failed: {e}', type='negative')

    # ── Save ─────────────────────────────────────────────────────────────────
    async def save():
        name = refs['name_input'].value.strip()
        if not name:
            ui.notify('Name is required', type='warning')
            return

        tool = state['selected_tool']
        is_new = state['is_new']

        new_tool = Tool(
            name=name,
            description=refs['desc_input'].value,
            code=refs['code_editor'].value,
            active=True if is_new else (tool.active if tool else True),
        )

        if is_new:
            success = tool_service.create_tool(new_tool)
        else:
            success = tool_service.update_tool(tool.name, new_tool)

        if success:
            ui.notify('Tool saved', type='success')
            refresh_list()
            # Stay on the saved tool (switch to edit mode)
            saved = tool_service.get_tool(name)
            if saved:
                load_tool_into_panel(saved, is_new=False)
        else:
            ui.notify('Error saving tool (name may already exist)', type='negative')

    # ── Delete ───────────────────────────────────────────────────────────────
    async def delete_tool_action(row):
        if row.get('is_builtin'):
            ui.notify('Builtin tools cannot be deleted', type='warning')
            return
        with ui.dialog() as dlg, ui.card():
            ui.label(f"Delete {row['name']}?").classes('font-bold')
            with ui.row().classes('justify-end w-full mt-4'):
                ui.button('Cancel', on_click=lambda: dlg.submit(False)).props('flat')
                ui.button('Delete', on_click=lambda: dlg.submit(True)).props('color=negative')
        if await dlg:
            if tool_service.delete_tool(row['name']):
                ui.notify(f"Deleted {row['name']}", type='success')
                refresh_list()
                # Clear panel if the deleted tool was selected
                if state['selected_tool'] and state['selected_tool'].name == row['name']:
                    load_tool_into_panel(None)
            else:
                ui.notify('Delete failed', type='negative')

    # ── Toggle Active ────────────────────────────────────────────────────────
    def toggle_active_action(row):
        if tool_service.toggle_tool_active(row['name']):
            refresh_list()

    # ═════════════════════════════════════════════════════════════════════════
    # UI Layout
    # ═════════════════════════════════════════════════════════════════════════
    with ui.column().classes('w-full h-full pt-14 px-4 max-w-7xl mx-auto gap-0'):

        # ── Page Header ──────────────────────────────────────────────────────
        with ui.row().classes('w-full justify-between items-center mb-4'):
            ui.label('Tools').classes(
                'text-3xl font-bold bg-clip-text text-transparent '
                'bg-gradient-to-r from-pink-400 to-orange-400'
            )
            ui.button(
                'New Tool',
                on_click=lambda: load_tool_into_panel(None, is_new=True),
                icon='add',
            ).props('color=secondary')

        # ── Split Layout ─────────────────────────────────────────────────────
        with ui.row().classes('w-full gap-4 items-start').style('min-height: calc(100vh - 130px)'):

            # ── Left — Tool List ─────────────────────────────────────────────
            with ui.column().classes('gap-2').style('width: 420px; flex-shrink: 0'):
                columns = [
                    {'name': 'active',     'label': 'Active',       'field': 'active',     'align': 'center'},
                    {'name': 'name',       'label': 'Name',         'field': 'name',       'align': 'left', 'sortable': True},
                    {'name': 'is_builtin', 'label': 'Type',         'field': 'is_builtin', 'align': 'center'},
                    {'name': 'actions',    'label': '',             'field': 'actions',    'align': 'right'},
                ]

                table = ui.table(
                    columns=columns, rows=[], row_key='name'
                ).classes('w-full glass-panel remove-defaults')

                # Slots
                table.add_slot('body-cell-active', r'''
                    <q-td key="active" :props="props">
                        <q-icon :name="props.row.active ? 'toggle_on' : 'toggle_off'"
                                :class="props.row.active ? 'text-green-400 cursor-pointer' : 'text-gray-500 cursor-pointer'"
                                size="md"
                                @click="$parent.$emit('toggle', props.row)">
                            <q-tooltip>Click to Toggle</q-tooltip>
                        </q-icon>
                    </q-td>
                ''')

                table.add_slot('body-cell-is_builtin', r'''
                    <q-td key="is_builtin" :props="props">
                        <q-badge v-if="props.row.is_builtin" color="indigo-10" text-color="indigo-2" label="Builtin" />
                        <q-badge v-else color="teal-10" text-color="teal-2" label="Custom" />
                    </q-td>
                ''')

                table.add_slot('body-cell-actions', r'''
                    <q-td key="actions" :props="props" class="flex gap-2 justify-end">
                        <q-btn v-if="!props.row.is_builtin" flat round color="secondary" icon="edit" size="sm"
                               @click="$parent.$emit('edit', props.row)" />
                        <q-btn v-if="!props.row.is_builtin" flat round color="negative" icon="delete" size="sm"
                               @click="$parent.$emit('delete', props.row)" />
                    </q-td>
                ''')

                table.on('rowclick', lambda e: load_tool_into_panel(Tool.from_dict(e.args['row'])))

                table.on('toggle', lambda e: toggle_active_action(e.args))
                table.on('edit',   lambda e: load_tool_into_panel(Tool.from_dict(e.args)))
                table.on('delete', lambda e: delete_tool_action(e.args))

            # ── Right — Editor Panel ─────────────────────────────────────────
            with ui.column().classes('flex-1 glass-panel rounded-xl p-5 gap-4').style('min-width: 0'):

                # Title row
                with ui.row().classes('w-full items-center justify-between'):
                    panel_title = ui.label('No tool selected').classes('text-xl font-semibold')
                    refs['panel_title'] = panel_title

                # Hint when nothing is selected
                panel_hint = ui.label('Select a tool from the list or create a new one.').classes(
                    'text-sm text-gray-400 italic'
                )
                refs['panel_hint'] = panel_hint

                # Name + Description row
                with ui.row().classes('w-full gap-4'):
                    name_input = ui.input('Name').classes('flex-1').props('disabled')
                    refs['name_input'] = name_input

                    desc_input = ui.input('Description (auto from docstring)').classes('flex-1').props('readonly')
                    refs['desc_input'] = desc_input

                # Code editor
                ui.label('Python Code').classes('text-sm text-gray-400')
                code_editor = ui.codemirror(
                    value='', language='python'
                ).classes('w-full border rounded').style('height: 380px').props('read-only')
                refs['code_editor'] = code_editor

                # Action row
                with ui.row().classes('w-full justify-between items-center mt-1'):
                    gen_docs_btn = ui.button(
                        'Generate Docs with AI',
                        on_click=generate_docs,
                        icon='auto_awesome',
                    ).props('flat color=secondary').props('disabled')
                    refs['gen_docs_btn'] = gen_docs_btn

                    save_btn = ui.button('Save', on_click=save).props('color=primary').props('disabled')
                    refs['save_btn'] = save_btn

    # ── Initial Load ─────────────────────────────────────────────────────────
    refresh_list()
    load_tool_into_panel(None)
