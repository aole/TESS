from nicegui import ui
from services.tool_service import tool_service, Tool
from utils.llm_client import client
import asyncio

def create_page():
    # ── State ────────────────────────────────────────────────────────────────
    state = {
        'selected_tool': None,   # Tool object currently loaded in the panel
        'is_new': False,         # True when creating a new tool
        'test_args': '{\n  "param1": "value1",\n  "param2": 123\n}',
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
            refs['gen_btn'].disable()
            refs['test_btn'].disable()
        else:
            refs['name_input'].enable()
            refs['code_editor'].props(remove='read-only')
            refs['gen_btn'].enable()
            refs['test_btn'].enable()

    def load_tool_into_panel(tool: Tool | None, is_new: bool = False):
        """Populate the right panel with the given tool (or empty for new)."""
        state['selected_tool'] = tool
        state['is_new'] = is_new

        if tool is None and not is_new:
            # Ready to create state
            refs['panel_title'].set_text('Create Tool')
            refs['name_input'].value = ''
            refs['desc_input'].value = ''
            refs['code_editor'].value = ''
            refs['name_input'].enable()
            refs['code_editor'].props(remove='read-only')
            refs['gen_btn'].enable()
            refs['test_btn'].enable()
            # refs['save_btn'].enable() is now always true
            refs['panel_hint'].set_text('Describe a tool below or start typing to create one.')
            refs['panel_hint'].set_visibility(True)
            return

        refs['panel_hint'].set_visibility(False)

        if is_new:
            refs['panel_title'].set_text('Create Tool')
            refs['name_input'].value = ''
            refs['desc_input'].value = ''
            refs['code_editor'].value = ''
            refs['name_input'].enable()
            refs['code_editor'].props(remove='read-only')
            refs['gen_btn'].enable()
            refs['test_btn'].enable()
            # refs['save_btn'].enable() is now always true
        else:
            refs['panel_title'].set_text(f'Edit — {tool.name}')
            refs['name_input'].value = tool.name
            refs['desc_input'].value = tool.description or ''
            refs['code_editor'].value = tool.code or ''
            # Builtin tools are read-only
            _set_panel_readonly(tool.is_builtin)
            if not tool.is_builtin:
                refs['name_input'].disable()  # Don't allow renaming

    # ── AI Generation ────────────────────────────────────────────────────────
    async def open_ai_generator():
        try:
            models_raw = await client.list_models()
            if not models_raw:
                ui.notify('No Ollama models found', type='warning')
                return
            model_options = [m['model'] for m in models_raw]
        except Exception as e:
            ui.notify(f'Failed to fetch models: {e}', type='negative')
            return

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6'):
            ui.label('Generate with AI').classes('text-xl font-bold mb-2')
            ui.label('Describe the tool or requested changes.').classes('text-sm text-gray-400 mb-4')

            prompt_input = ui.textarea('Instructions').classes('w-full').props(
                'autofocus placeholder="e.g., Create a tool that calculates the fibonacci sequence"'
            )

            model_select = ui.select(
                options=model_options,
                value=model_options[0],
                label='Select LLM'
            ).classes('w-full mt-2')

            async def start_generation():
                instructions = prompt_input.value.strip()
                if not instructions:
                    ui.notify('Please provide instructions', type='warning')
                    return

                selected_model = model_select.value
                current_code = refs['code_editor'].value
                dialog.close()

                # Replace button with spinner
                refs['gen_btn'].set_visibility(False)
                refs['gen_spinner'].set_visibility(True)

                try:
                    context = f"\n\nCurrent code:\n```python\n{current_code}\n```" if current_code.strip() else ""
                    prompt = (
                        "You are an expert Python developer. "
                        + ("Modify the existing tool" if current_code.strip() else "Create a new tool")
                        + " based on the following instructions.\n\n"
                        "Requirements:\n"
                        "1. Return ONLY valid Python code.\n"
                        "2. DO NOT include markdown formatting, backticks, or any explanation.\n"
                        "3. Include a detailed docstring INSIDE the main function (Google/NumPy style).\n"
                        "4. Include type hints for all function arguments and return types.\n"
                        "5. The tool should be a complete, runnable Python module.\n\n"
                        "Example Format:\n"
                        "import math\n\n"
                        "def calculate_distance(x1: float, y1: float, x2: float, y2: float) -> float:\n"
                        '    """\n'
                        '    Calculate the distance between two points.\n\n'
                        '    Args:\n'
                        '        x1 (float): X-coord of first point.\n'
                        '        ...\n'
                        '    Returns:\n'
                        '        float: The distance.\n'
                        '    """\n'
                        '    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)\n\n'
                        f"Instructions: {instructions}"
                        + context
                    )

                    response_text = ''
                    gen = await client.generate(model=selected_model, prompt=prompt)
                    async for chunk in gen:
                        response_text += chunk.get('response', '')

                    cleaned = response_text.strip()
                    for prefix in ('```python', '```'):
                        if cleaned.startswith(prefix):
                            cleaned = cleaned[len(prefix):]
                    if cleaned.endswith('```'):
                        cleaned = cleaned[:-3]

                    refs['code_editor'].value = cleaned.strip()
                    ui.notify('Tool updated by AI', type='success')
                    # Ensure we are in "is_new" or edit mode now
                    if state['selected_tool'] is None:
                        state['is_new'] = True
                        refs['panel_hint'].set_visibility(False)
                except Exception as e:
                    ui.notify(f'AI generation failed: {e}', type='negative')
                finally:
                    refs['gen_btn'].set_visibility(True)
                    refs['gen_spinner'].set_visibility(False)

            with ui.row().classes('w-full justify-end mt-4 gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Generate', on_click=start_generation).props('color=primary icon=bolt')

        dialog.open()

    # ── Test Tool ────────────────────────────────────────────────────────────
    async def test_tool():
        code = refs['code_editor'].value
        if not code.strip():
            ui.notify('No code to test', type='warning')
            return

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6'):
            dialog.props('position=left')
            ui.label('Test Tool').classes('text-xl font-bold mb-2')
            ui.label('Provide arguments in JSON format:').classes('text-sm text-gray-400 mb-2')

            args_input = ui.textarea('Arguments (JSON)').classes('w-full').props(
                'autofocus placeholder=\'{"param": "value"}\''
            )
            args_input.value = state['test_args']

            ui.label('Output:').classes('mt-4 text-sm text-gray-400')
            output_area = ui.label('').classes(
                'w-full p-4 bg-black/20 rounded font-mono text-sm break-all whitespace-pre-wrap'
            )

            async def run_test():
                try:
                    import json
                    import traceback
                    
                    # Store current arguments for next time
                    state['test_args'] = args_input.value
                    
                    args = json.loads(args_input.value or '{}')

                    # Setup namespace and exec code
                    ns = {}
                    # Inject common utilities if needed
                    exec(code, ns)

                    # Find the tool function (first callable that is not a builtin/import)
                    funcs = [v for k, v in ns.items() if callable(v) and not k.startswith('__')]
                    if not funcs:
                        output_area.set_text('Error: No function found in code.')
                        return

                    target_func = funcs[0]
                    ui.notify(f'Running {target_func.__name__}...', type='info')

                    # Execute (handle both async and sync)
                    if asyncio.iscoroutinefunction(target_func):
                        result = await target_func(**args)
                    else:
                        result = target_func(**args)

                    output_area.set_text(str(result))
                except Exception as e:
                    output_area.set_text(f"Error: {e}\n\n{traceback.format_exc()}")

            with ui.row().classes('w-full justify-end mt-4 gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Run Test', on_click=run_test).props('color=primary icon=play_arrow')

        dialog.open()

    # ── Save ─────────────────────────────────────────────────────────────────
    async def save():
        name = refs['name_input'].value.strip()
        if not name:
            ui.notify('Name is required', type='warning')
            return

        tool = state['selected_tool']
        if tool and tool.is_builtin:
            ui.notify('Builtin tools cannot be modified', type='warning')
            return

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
                    name_input = ui.input('Name')
                    name_input.classes('flex-1')
                    refs['name_input'] = name_input

                    desc_input = ui.input('Description (auto from docstring)').classes('flex-1').props('readonly')
                    refs['desc_input'] = desc_input

                # Code editor
                ui.label('Python Code').classes('text-sm text-gray-400')
                code_editor = ui.codemirror(
                    value='', language='python', theme='dracula'
                ).classes('w-full border border-gray-700 rounded-lg shadow-inner').style('height: 480px').props('read-only')
                refs['code_editor'] = code_editor

                # Action row
                with ui.row().classes('w-full justify-between items-center mt-1'):
                    with ui.row().classes('items-center'):
                        gen_btn = ui.button(
                            'Generate with AI',
                            on_click=open_ai_generator,
                            icon='psychology',
                        ).props('flat color=secondary')
                        refs['gen_btn'] = gen_btn

                        gen_spinner = ui.spinner(size='md', color='secondary').classes('ml-2')
                        gen_spinner.set_visibility(False)
                        refs['gen_spinner'] = gen_spinner

                    with ui.row().classes('items-center gap-2'):
                        test_btn = ui.button(
                            'Test',
                            on_click=test_tool,
                            icon='play_arrow',
                        ).props('flat color=primary')
                        refs['test_btn'] = test_btn

                        save_btn = ui.button('Save', on_click=save).props('color=primary')
                        refs['save_btn'] = save_btn

    # ── Initial Load ─────────────────────────────────────────────────────────
    refresh_list()
    load_tool_into_panel(None)
