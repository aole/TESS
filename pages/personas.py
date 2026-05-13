from nicegui import ui
from services.persona_service import persona_service
from utils.ui_components import ui_list, ui_list_item, ui_card


# ── State ────────────────────────────────────────────────────────────────────
_selected_id: str | None = None


def create_page():
    global _selected_id
    _selected_id = None

    # ── Two-panel layout ──────────────────────────────────────────────────────
    with ui.row().classes('w-full min-h-screen gap-0 items-start pt-14'):

        # ════════════════════════════════════════════════════════════════════
        # LEFT PANEL — Persona List
        # ════════════════════════════════════════════════════════════════════
        with ui.column().classes(
            'w-80 shrink-0 min-h-screen border-r border-white/10 '
            'bg-black/20 sticky top-14 self-start overflow-y-auto'
        ).style('max-height: calc(100vh - 3.5rem)'):

            list_body = ui_list(
                heading='Personas',
                heading_icon='person',
                action_icon='add',
                action_tooltip='New Persona',
                on_action=lambda: open_create_form(),
            )

        # ════════════════════════════════════════════════════════════════════
        # RIGHT PANEL — Edit / Detail Panel
        # ════════════════════════════════════════════════════════════════════
        with ui.column().classes('flex-1 p-8 gap-6 max-w-3xl'):

            # Page heading
            with ui.row().classes('items-center gap-3 w-full'):
                ui.icon('person', size='32px').classes('text-purple-400')
                ui.label('Personas').classes(
                    'text-3xl font-bold bg-clip-text text-transparent '
                    'bg-gradient-to-r from-purple-400 to-pink-400'
                )

            # Empty-state / form container
            form_container = ui.column().classes('w-full gap-6')

            with form_container:
                _render_empty_state()

        # ── Wire everything up ────────────────────────────────────────────────

        def render_list():
            list_body.clear()
            personas = persona_service.get_personas()
            with list_body:
                if not personas:
                    ui.label('No personas yet').classes(
                        'text-xs text-gray-500 italic px-4 py-6 text-center'
                    )
                for p in personas:
                    pid = p['id']
                    with ui_list_item(
                        title=p['name'],
                        subtitle=_preview(p['system_prompt']),
                        active=(pid == _selected_id),
                        on_click=lambda _p=p: open_edit_form(_p),
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
            # Re-open the updated persona
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
                'bg-[#1e1f20] border border-white/10 p-6 w-96'
            ):
                ui.label(f'Delete "{name}"?').classes(
                    'text-xl font-bold text-gray-200 mb-2'
                )
                ui.label('This action cannot be undone.').classes(
                    'text-gray-400 text-sm mb-6'
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

        # Initial render
        render_list()


# ── Helper renderers (stateless) ─────────────────────────────────────────────

def _preview(text: str, max_len: int = 50) -> str:
    text = text.strip().replace('\n', ' ')
    return text[:max_len] + '…' if len(text) > max_len else text


def _render_empty_state():
    with ui.column().classes('w-full items-center justify-center py-24 gap-4 text-center'):
        ui.icon('person_outline', size='64px').classes('text-purple-400/30')
        ui.label('Select a persona to edit').classes('text-xl font-semibold text-gray-400')
        ui.label(
            'Or click the + button on the left to create a new one.'
        ).classes('text-sm text-gray-600')


def _render_create_form(on_save, on_cancel):
    with ui_card(
        heading='New Persona',
        heading_icon='add_circle',
        heading_color='purple',
        collapsible=False,
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
        placeholder='e.g. Helpful Assistant, Code Expert…',
        value=name_val,
    ).classes('w-full').props('outlined dark')

    ui.label('System Prompt').classes('text-sm font-semibold text-gray-400 mt-2')
    prompt_input = ui.textarea(
        placeholder='You are a helpful assistant that…',
        value=prompt_val,
    ).classes('w-full font-mono text-sm').props('outlined dark rows=12')

    with ui.row().classes('w-full justify-between items-center mt-4'):
        # Left: delete (only for existing)
        if on_delete:
            ui.button(
                'Delete',
                icon='delete',
                on_click=on_delete,
            ).props('flat color=negative').classes('text-sm')
        else:
            ui.element('div')  # spacer

        # Right: cancel / save
        with ui.row().classes('gap-2'):
            ui.button('Cancel', on_click=on_cancel).props('flat color=grey')
            ui.button(
                save_label,
                icon=save_icon,
                on_click=lambda: on_save(name_input.value, prompt_input.value),
            ).props('color=secondary').classes('font-semibold')

