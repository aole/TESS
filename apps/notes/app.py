from nicegui import ui
from services.note_service import note_service
from utils.config import config_manager
from datetime import datetime, timedelta
import threading

def render():
    # Page Container
    with ui.column().classes('w-full max-w-[1000px] mx-auto p-6 gap-6'):

        # ── Header ────────────────────────────────────────────────────────────
        with ui.row().classes('w-full justify-between items-center'):
            with ui.column().classes('gap-0'):
                ui.label('Notes').classes('text-3xl font-bold text-gray-200')
                ui.label('Capture your thoughts and ideas').classes('text-sm text-gray-400')

            # Sync button + status label
            with ui.row().classes('items-center gap-2'):
                sync_status = ui.label('').classes('text-xs text-gray-500')
                sync_btn = ui.button(icon='sync', on_click=lambda: do_sync()) \
                    .props('flat round color=grey') \
                    .tooltip('Sync with Google Drive')

        # ── Input Area ────────────────────────────────────────────────────────
        with ui.card().classes('w-full p-0 gap-0 bg-[#1e1f20] border border-white/10 rounded-xl overflow-hidden'):
            with ui.column().classes('w-full p-4 gap-2'):
                note_input = ui.textarea(placeholder="What's on your mind?") \
                    .props('autogrow borderless text-color=white input-class="text-lg"') \
                    .classes('w-full')

                with ui.row().classes('w-full justify-between items-center pt-2 border-t border-white/5'):
                    ui.label(datetime.now().strftime("%B %d, %Y")).classes('text-xs text-gray-500 pl-1')

                    with ui.row().classes('items-center gap-2'):
                        categories = config_manager.get_note_categories()
                        default_cat = "General" if "General" in categories else (categories[0] if categories else "")
                        cat_select = ui.select(
                            categories, value=default_cat,
                            on_change=lambda: refresh_notes()
                        ).props('dense options-dense borderless bg-color=transparent') \
                         .classes('w-32 text-sm text-gray-400')

                        ui.button('Save Note', on_click=lambda: add_note()) \
                            .props('flat no-caps icon=save color=primary')

        # Enter-to-save shortcut
        note_input.on(
            'keydown.enter.exact',
            lambda e: add_note() if not e.args['shiftKey'] else None,
            args=['shiftKey']
        )

        # ── Notes List ────────────────────────────────────────────────────────
        notes_container = ui.column().classes('w-full gap-0')

        def format_date(iso_str):
            try:
                dt = datetime.fromisoformat(iso_str)
                return dt.strftime("%d-%b-%y %H:%M")
            except Exception:
                return iso_str

        def refresh_notes():
            notes_container.clear()
            notes = note_service.get_notes()
            selected_cat = cat_select.value

            filtered_notes = [n for n in notes if n.get('category', 'General') == selected_cat]

            with notes_container:
                if not filtered_notes:
                    with ui.column().classes('w-full items-center justify-center py-12 opacity-50'):
                        ui.icon('edit_note', size='48px').classes('text-gray-500 mb-2')
                        ui.label(f'No notes in {selected_cat}').classes('text-gray-500')

                for note in filtered_notes:
                    with ui.row().classes('w-full items-start group relative p-1 hover:bg-white/5 rounded transition-colors gap-2'):
                        ts = format_date(note['timestamp'])
                        content = note['content']

                        import html
                        import re
                        safe_content = html.escape(content)
                        url_pattern = re.compile(r'(https?://\S+)')
                        safe_content = url_pattern.sub(
                            r'<a href="\1" target="_blank" class="text-secondary hover:underline">\1</a>',
                            safe_content
                        )

                        ui.html(f'''
                            <div class="text-sm text-gray-200 font-sans break-words overflow-hidden">
                                <span class="text-purple-400 font-mono text-xs mr-1 opacity-80">{ts}:</span>
                                <span class="whitespace-pre-wrap">{safe_content}</span>
                            </div>
                        ''', sanitize=False).classes('flex-grow')

                        ui.button(
                            icon='close',
                            on_click=lambda _, n=note: delete_note(n['id'])
                        ).props('flat round dense size=xs color=grey') \
                         .classes('opacity-0 group-hover:opacity-100 transition-opacity absolute right-1 top-1')

        def add_note():
            content = note_input.value.strip()
            if content:
                try:
                    note_service.add_note(content, category=cat_select.value)
                    note_input.value = ''
                    refresh_notes()
                    ui.notify(f'Note saved to {cat_select.value}', type='positive')
                except Exception as e:
                    ui.notify(f'Failed to save: {e}', type='negative')

        def delete_note(note_id):
            note_service.delete_note(note_id)
            ui.notify('Note deleted', type='info')
            refresh_notes()

        def _format_sync_time(iso: str) -> str:
            """Return a human-readable 'Synced HH:MM' or 'Synced Jan 12 HH:MM' string."""
            try:
                dt = datetime.fromisoformat(iso)
                now = datetime.now()
                if dt.date() == now.date():
                    return f'Synced {dt.strftime("%H:%M")}'
                return f'Synced {dt.strftime("%b %d %H:%M")}'
            except Exception:
                return ''

        def do_sync(*, silent=False):
            """Sync with Drive; refresh UI when done."""
            sync_btn.props('loading')
            sync_status.set_text('Syncing…')

            def _run():
                try:
                    count = note_service.sync_notes()
                    if count == -1:
                        # Drive not available
                        sync_status.set_text('No Drive account')
                        if not silent:
                            ui.notify('No Google account connected — notes saved locally only.', type='warning')
                    else:
                        last_iso = config_manager.get_last_notes_sync()
                        sync_status.set_text(_format_sync_time(last_iso))
                        refresh_notes()
                        if not silent:
                            ui.notify('Notes synced with Google Drive', type='positive')
                except Exception as e:
                    sync_status.set_text('Sync failed')
                    if not silent:
                        ui.notify(f'Sync error: {e}', type='negative')
                finally:
                    sync_btn.props(remove='loading')

            threading.Thread(target=_run, daemon=True).start()

        # ── Initial Load ──────────────────────────────────────────────────────
        def on_load():
            refresh_notes()

            # Seed status label from persisted timestamp
            last_iso = config_manager.get_last_notes_sync()
            if last_iso:
                sync_status.set_text(_format_sync_time(last_iso))

            # Auto-sync only if last sync was more than 24 hours ago (or never)
            should_sync = True
            if last_iso:
                try:
                    last_dt = datetime.fromisoformat(last_iso)
                    if datetime.now() - last_dt < timedelta(hours=24):
                        should_sync = False
                except Exception:
                    pass

            if should_sync:
                do_sync(silent=True)

        ui.timer(0, on_load, once=True)
