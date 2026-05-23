from nicegui import ui

from services.persona_service import persona_service
from services.system_message_service import system_message_service
from utils.ui_components import ui_card, ui_list, ui_list_item


_selected_id: str | None = None


def create_page():
    global _selected_id
    _selected_id = None

    with ui.column().classes(
        'w-full pt-2 pb-2 px-4 mx-auto gap-0'
    ).style('height: calc(100vh - 64px); overflow: hidden;'):

        with ui.row().classes('w-full justify-between items-center mb-2'):
            ui.label('Personas').classes(
                'text-3xl font-bold bg-clip-text text-transparent '
                'bg-gradient-to-r from-purple-400 to-pink-400'
            )

        with ui.row().classes(
            'w-full gap-4 items-stretch flex-nowrap flex-grow'
        ).style('min-height: 0;'):

            with ui.column().classes(
                'glass-panel rounded-xl p-0 gap-0'
            ).style(
                'width: 320px; flex-shrink: 0; height: 100%; '
                'display: flex; flex-direction: column;'
            ):
                list_body = ui_list(
                    heading='Personas',
                    heading_icon='person',
                    action_icon='add',
                    action_tooltip='New Persona',
                    on_action=lambda: open_create_form(),
                )

            with ui.column().classes(
                'flex-1 glass-panel rounded-xl p-3 gap-3 min-w-0'
            ).style('height: 100%; display: flex; flex-direction: column;'):
                form_container = ui.column().classes('w-full gap-3 flex-grow min-h-0')

                with form_container:
                    _render_empty_state()

            with ui.column().classes(
                'glass-panel rounded-xl p-3 gap-2 overflow-y-auto'
            ).style(
                'width: 300px; flex-shrink: 0; height: 100%; '
                'display: flex; flex-direction: column;'
            ):
                _render_variables_reference()

        def render_list():
            list_body.clear()
            personas = persona_service.get_personas()
            with list_body:
                if not personas:
                    ui.label('No personas yet').classes(
                        'text-xs text-gray-500 italic px-4 py-6 text-center'
                    )
                for persona in personas:
                    pid = persona['id']
                    with ui_list_item(
                        title=persona['name'],
                        subtitle=_preview(persona['system_prompt']),
                        active=(pid == _selected_id),
                        on_click=lambda _p=persona: open_edit_form(_p),
                        action_icon='delete',
                        action_color='red-4',
                        action_tooltip='Delete',
                        on_action=lambda _pid=pid: confirm_delete(_pid),
                    ):
                        pass

        def open_create_form():
            global _selected_id
            _selected_id = None
            render_list()
            form_container.clear()
            with form_container:
                _render_create_form(on_save=_on_save_new, on_cancel=_on_cancel)

        def open_edit_form(persona: dict):
            global _selected_id
            _selected_id = persona['id']
            render_list()
            form_container.clear()
            with form_container:
                _render_edit_form(
                    persona=persona,
                    on_save=lambda name, prompt: _on_save_edit(persona['id'], name, prompt),
                    on_cancel=_on_cancel,
                    on_delete=lambda: confirm_delete(persona['id']),
                )

        def _on_save_new(name: str, prompt: str):
            if not name.strip():
                ui.notify('Name is required', type='warning')
                return
            persona_service.add_persona(name, prompt)
            ui.notify(f'Persona "{name}" created', type='positive')
            global _selected_id
            _selected_id = None
            render_list()
            form_container.clear()
            with form_container:
                _render_empty_state()

        def _on_save_edit(pid: str, name: str, prompt: str):
            if not name.strip():
                ui.notify('Name is required', type='warning')
                return
            persona_service.update_persona(pid, name, prompt)
            ui.notify(f'Persona "{name}" saved', type='positive')
            updated = persona_service.get_persona(pid)
            if updated:
                open_edit_form(updated)
            else:
                _on_cancel()

        def _on_cancel():
            global _selected_id
            _selected_id = None
            render_list()
            form_container.clear()
            with form_container:
                _render_empty_state()

        async def confirm_delete(pid: str):
            persona = persona_service.get_persona(pid)
            name = persona['name'] if persona else 'this persona'
            with ui.dialog() as dlg, ui.card().classes(
                'bg-[#1e1f20] border border-white/10 p-5 w-96'
            ):
                ui.label(f'Delete "{name}"?').classes(
                    'text-xl font-bold text-gray-200 mb-2'
                )
                ui.label('This action cannot be undone.').classes(
                    'text-gray-400 text-sm mb-4'
                )
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=lambda: dlg.submit(False)).props(
                        'flat color=grey'
                    )
                    ui.button('Delete', on_click=lambda: dlg.submit(True)).props(
                        'flat color=negative'
                    )
            if await dlg:
                persona_service.delete_persona(pid)
                ui.notify(f'Deleted "{name}"', type='negative')
                global _selected_id
                if _selected_id == pid:
                    _selected_id = None
                render_list()
                form_container.clear()
                with form_container:
                    _render_empty_state()

        render_list()


def _preview(text: str, max_len: int = 50) -> str:
    text = text.strip().replace('\n', ' ')
    return text[:max_len] + '...' if len(text) > max_len else text


def _render_empty_state():
    with ui.column().classes(
        'w-full h-full items-center justify-center py-12 gap-3 text-center'
    ):
        ui.icon('person_outline', size='52px').classes('text-purple-400/30')
        ui.label('Select a persona to edit').classes('text-lg font-semibold text-gray-400')
        ui.label('Use New Persona to create one.').classes('text-sm text-gray-600')


def _render_variables_reference():
    refs = {}

    def copy_variable(name: str):
        ui.run_javascript(f"navigator.clipboard.writeText('{{{{{name}}}}}')")
        ui.notify(f"Copied {{{{{name}}}}} to clipboard", type='positive')

    def render_variables():
        variables_container = refs['variables_container']
        variables_container.clear()
        with variables_container:
            builtins = system_message_service.get_builtin_variables()
            custom_vars = system_message_service.get_custom_variables()

            ui.label('Built-in').classes(
                'text-[11px] font-bold text-gray-500 uppercase tracking-widest mt-1'
            )
            for var in builtins:
                _render_variable_row(
                    name=var['name'],
                    value=var['value'],
                    on_copy=lambda _name=var['name']: copy_variable(_name),
                )

            with ui.row().classes('w-full items-center justify-between mt-2'):
                ui.label('Custom').classes(
                    'text-[11px] font-bold text-gray-500 uppercase tracking-widest'
                )
                ui.button(
                    icon='add',
                    on_click=open_variable_form,
                ).props('flat round dense size=sm color=secondary').tooltip('Add variable')

            if not custom_vars:
                ui.label('No custom variables').classes(
                    'text-xs text-gray-500 italic px-1 py-2'
                )
            for var in custom_vars:
                _render_variable_row(
                    name=var['name'],
                    value=var.get('value', ''),
                    editable=True,
                    on_copy=lambda _name=var['name']: copy_variable(_name),
                    on_edit=lambda _var=var: open_variable_form(_var),
                    on_delete=lambda _id=var['id']: delete_variable(_id),
                )

    def save_variable(name_input, value_input, dialog, variable: dict | None = None):
        if variable:
            ok, message = system_message_service.update_custom_variable(
                variable['id'],
                name_input.value or '',
                value_input.value or '',
            )
        else:
            ok, message = system_message_service.add_custom_variable(
                name_input.value or '',
                value_input.value or '',
            )

        if not ok:
            ui.notify(message, type='warning')
            return

        ui.notify(f'Variable {message} saved', type='positive')
        dialog.close()
        render_variables()

    def open_variable_form(variable: dict | None = None):
        with ui.dialog() as dialog, ui.card().classes(
            'bg-[#1e1f20] border border-white/10 p-4 w-full max-w-md gap-3'
        ):
            ui.label('Edit Variable' if variable else 'New Variable').classes(
                'text-lg font-bold text-gray-200'
            )
            name_input = ui.input(
                'Name',
                value=variable['name'] if variable else '',
                placeholder='PROJECT_NAME',
            ).classes('w-full').props('outlined dark dense autofocus')
            value_input = ui.textarea(
                'Value',
                value=variable.get('value', '') if variable else '',
                placeholder='Literal value or @file(notes.txt)',
            ).classes('w-full').props('outlined dark rows=3')
            ui.label(
                'Use @file(path/to/file.txt) to insert a text file from data or a subfolder.'
            ).classes('text-xs text-gray-500')

            with ui.row().classes('w-full justify-end gap-2 mt-1'):
                ui.button('Cancel', on_click=dialog.close).props('flat color=grey')
                ui.button(
                    'Save',
                    icon='save',
                    on_click=lambda: save_variable(name_input, value_input, dialog, variable),
                ).props('color=secondary')
        dialog.open()

    def delete_variable(variable_id: str):
        if system_message_service.delete_custom_variable(variable_id):
            ui.notify('Variable deleted', type='negative')
            render_variables()

    with ui.row().classes('items-center justify-between w-full'):
        with ui.row().classes('items-center gap-2'):
            ui.icon('token', size='18px').classes('text-purple-400')
            ui.label('System Variables').classes('text-base font-bold text-gray-200')

    ui.label(
        'Use {{VARIABLE_NAME}} in prompts. Values can be literal text or @file(path/to/file.txt) from data.'
    ).classes('text-xs text-gray-400 leading-relaxed mb-1')

    refs['variables_container'] = ui.column().classes('w-full gap-1.5')
    render_variables()


def _render_variable_row(
    *,
    name: str,
    value: str,
    editable: bool = False,
    on_copy,
    on_edit=None,
    on_delete=None,
):
    with ui.element('div').classes(
        'w-full px-2 py-1.5 rounded-md bg-white/5 border border-white/5 '
        'hover:border-purple-500/30 transition-colors'
    ):
        with ui.row().classes('w-full items-center gap-1.5 flex-nowrap'):
            ui.label(f'{{{{{name}}}}}').classes(
                'text-[11px] font-mono font-semibold text-purple-300 truncate flex-1 min-w-0'
            ).on('click', lambda _: on_copy())

            if editable:
                ui.button(icon='edit', on_click=on_edit).props(
                    'flat round dense size=xs color=grey'
                ).tooltip('Edit')
                ui.button(icon='delete', on_click=on_delete).props(
                    'flat round dense size=xs color=negative'
                ).tooltip('Delete')
            ui.button(icon='content_copy', on_click=on_copy).props(
                'flat round dense size=xs color=primary'
            ).tooltip('Copy')

        if value:
            ui.label(value).classes('text-[11px] text-gray-500 font-mono truncate')


def _render_create_form(on_save, on_cancel):
    with ui_card(
        heading='New Persona',
        heading_icon='add_circle',
        heading_color='purple',
        collapsible=False,
        extra_classes='p-4',
    ):
        _persona_form(
            name_val='',
            prompt_val='',
            save_label='Create Persona',
            save_icon='add',
            on_save=on_save,
            on_cancel=on_cancel,
        )


def _render_edit_form(persona: dict, on_save, on_cancel, on_delete):
    with ui_card(
        heading=f'Edit: {persona["name"]}',
        heading_icon='edit',
        heading_color='purple',
        collapsible=False,
        extra_classes='p-4',
    ):
        _persona_form(
            name_val=persona['name'],
            prompt_val=persona['system_prompt'],
            save_label='Save Changes',
            save_icon='save',
            on_save=on_save,
            on_cancel=on_cancel,
            on_delete=on_delete,
        )


def _persona_form(
    *,
    name_val: str,
    prompt_val: str,
    save_label: str,
    save_icon: str,
    on_save,
    on_cancel,
    on_delete=None,
):
    name_input = ui.input(
        label='Persona Name',
        placeholder='e.g. Helpful Assistant, Code Expert...',
        value=name_val,
    ).classes('w-full').props('outlined dark dense')

    ui.label('System Prompt').classes('text-sm font-semibold text-gray-400 mt-1')
    prompt_input = ui.textarea(
        placeholder='You are a helpful assistant that...',
        value=prompt_val,
    ).classes('w-full font-mono text-sm').props('outlined dark rows=12')

    with ui.row().classes('w-full justify-between items-center mt-3'):
        if on_delete:
            ui.button(
                'Delete',
                icon='delete',
                on_click=on_delete,
            ).props('flat color=negative').classes('text-sm')
        else:
            ui.element('div')

        with ui.row().classes('gap-2'):
            ui.button('Cancel', on_click=on_cancel).props('flat color=grey')
            ui.button(
                save_label,
                icon=save_icon,
                on_click=lambda: on_save(name_input.value, prompt_input.value),
            ).props('color=secondary').classes('font-semibold')
