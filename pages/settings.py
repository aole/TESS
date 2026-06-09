from nicegui import ui, app, run
from utils.config import config_manager
from utils.ui_components import ui_card, ui_info_card
from services.note_service import note_service
from services.tts_service import VOICES, tts_service
from services.persona_service import persona_service
import asyncio

# ── Storage key used to persist system info for the session ──────────────────
_SYS_INFO_KEY = "system_info_cache"


def _icon_row(icon: str, label: str, value: str, icon_color: str = "indigo"):
    """Helper: one info row with a material icon, label, and value."""
    with ui.row().classes("items-start gap-3 w-full"):
        ui.icon(icon, size="18px").classes(f"text-{icon_color}-400 mt-0.5 shrink-0")
        with ui.column().classes("gap-0 min-w-0"):
            ui.label(label).classes("text-xs text-gray-500 uppercase tracking-wider")
            ui.label(value).classes("text-sm text-gray-200 font-medium break-words")


def _build_system_panel(info: dict, container: ui.column):
    """Render system info cards inside the given container."""
    container.clear()
    with container:
        # ── OS & Hardware ─────────────────────────────────────────────────────
        with ui_info_card(heading="System", heading_color="indigo"):
            with ui.column().classes("gap-3 w-full"):
                _icon_row("computer", "Operating System", info.get("os", "—"))
                _icon_row("memory", "CPU", info.get("cpu", "—"), "purple")
                _icon_row("storage", "Architecture", info.get("arch", "—"), "blue")
                _icon_row("database", "Disk", info.get("disk", "—"), "cyan")
                _icon_row("developer_board", "RAM", info.get("ram", "—"), "green")

        # ── GPUs ─────────────────────────────────────────────────────────────
        with ui_info_card(heading="Graphics", heading_color="purple"):
            gpus = info.get("gpus", [])
            if gpus:
                with ui.column().classes("gap-3 w-full"):
                    for i, gpu in enumerate(gpus, 1):
                        name = gpu.get("name", "Unknown")
                        vram = gpu.get("vram", "")
                        display = f"{name} ({vram})" if vram and vram != "Unknown" else name
                        _icon_row("videocam", f"GPU {i}", display, "pink")
            else:
                ui.label("No GPU detected").classes("text-sm text-gray-500 italic")

        # ── Software ─────────────────────────────────────────────────────────
        with ui_info_card(heading="Software", heading_color="emerald"):
            with ui.column().classes("gap-3 w-full"):
                _icon_row("code", "Python", info.get("python", "—"), "yellow")
                _icon_row("bolt", "CUDA", info.get("cuda", "—"), "orange")
                _icon_row("smart_toy", "Ollama", info.get("ollama", "—"), "teal")


async def _query_system(info_column: ui.column, status_label: ui.label, query_btn: ui.button):
    """Fetch system info, persist in session, and render."""
    query_btn.props("loading")
    status_label.set_text("Gathering system information…")
    status_label.classes(remove="text-gray-500", add="text-indigo-400")
    try:
        from services.system_service import collect_system_info
        info = await run.io_bound(collect_system_info)
        app.storage.user[_SYS_INFO_KEY] = info
        _build_system_panel(info, info_column)
        status_label.set_text("Last updated just now ✓")
        status_label.classes(remove="text-indigo-400", add="text-emerald-400")
        query_btn.set_text("Re-query System")
    except Exception as ex:
        status_label.set_text(f"Error: {ex}")
        status_label.classes(remove="text-indigo-400", add="text-red-400")
    finally:
        query_btn.props(remove="loading")


def create_page():
    # ── Outer: side-by-side layout ────────────────────────────────────────────
    with ui.row().classes("w-full min-h-screen gap-0 items-start pt-14"):

        # ════════════════════════════════════════════════════════════════════
        # LEFT PANEL — System Information
        # ════════════════════════════════════════════════════════════════════
        with ui.column().classes(
            "w-100 shrink-0 min-h-screen p-4 gap-4 border-r border-white/10 "
            "bg-black/20 sticky top-14 self-start overflow-y-auto"
        ).style("max-height: calc(100vh - 3.5rem)"):

            # Header row
            with ui.row().classes("items-center gap-2 w-full"):
                ui.icon("wysiwyg", size="20px").classes("text-indigo-400")
                ui.label("System Info").classes("text-base font-bold text-gray-200")

            # Check cache before rendering anything else so button label is correct
            cached = app.storage.user.get(_SYS_INFO_KEY)
            _has_cache = bool(cached)

            # ── Button at the top ─────────────────────────────────────────────
            _btn_label = "Re-query System" if _has_cache else "Query System"
            query_btn = ui.button(
                _btn_label,
                icon="search",
                on_click=lambda: _query_system(info_column, status_label, query_btn),
            ).classes(
                "w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg "
                "text-sm font-semibold transition-all duration-200"
            ).props("no-caps")

            status_label = ui.label("Not yet queried").classes("text-xs text-gray-500")

            # Container where the cards will be injected
            info_column = ui.column().classes("gap-3 w-full")

            # Restore cached data if already queried this session
            if cached:
                _build_system_panel(cached, info_column)
                status_label.set_text("Restored from session ✓")
                status_label.classes(remove="text-gray-500", add="text-emerald-400")

        # ════════════════════════════════════════════════════════════════════
        # RIGHT PANEL — Settings Content
        # ════════════════════════════════════════════════════════════════════
        with ui.column().classes("flex-1 p-4 gap-4 max-w-3xl"):

            ui.label('Settings').classes(
                'text-3xl font-bold bg-clip-text text-transparent '
                'bg-gradient-to-r from-indigo-400 to-purple-400'
            )

            # ── Logging ───────────────────────────────────────────────────────
            def _logging_footer():
                with ui.row().classes('items-center justify-between w-full'):
                    ui.markdown("> Logs are saved to `logs/llm_debug.log`").classes("text-sm text-gray-500 italic")
                    
                    with ui.row().classes('items-center gap-3'):
                        def _show_logs():
                            with ui.dialog() as dialog, ui.card().classes('bg-[#1e1f20] border border-white/10 p-6 w-[90vw] max-w-5xl h-[85vh] flex flex-col'):
                                with ui.column().classes('w-full h-full gap-4 items-stretch'):
                                    with ui.row().classes('w-full justify-between items-center mb-4 shrink-0'):
                                        with ui.row().classes('items-center gap-2'):
                                            ui.icon('article', size='24px').classes('text-indigo-400')
                                            ui.label('LLM Debug Logs').classes('text-xl font-bold text-gray-200')
                                        with ui.row().classes('items-center gap-2'):
                                            is_wrapped = False
                                            def toggle_wrap():
                                                nonlocal is_wrapped
                                                is_wrapped = not is_wrapped
                                                if is_wrapped:
                                                    log_label.classes(remove='whitespace-pre', add='whitespace-pre-wrap break-all')
                                                    wrap_btn.props('color=accent')
                                                else:
                                                    log_label.classes(remove='whitespace-pre-wrap break-all', add='whitespace-pre')
                                                    wrap_btn.props('color=primary')
                                            
                                            wrap_btn = ui.button(icon='wrap_text', on_click=toggle_wrap).props('flat round color=primary').tooltip('Toggle Word Wrap')
                                            ui.button(icon='refresh', on_click=lambda: asyncio.create_task(_load_logs())).props('flat round color=primary').tooltip('Refresh Logs')
                                            ui.button(icon='content_copy', on_click=lambda: asyncio.create_task(_copy_logs())).props('flat round color=secondary').tooltip('Copy to Clipboard')
                                            
                                            def _clear_logs_from_popup():
                                                with ui.dialog() as confirm_dialog, ui.card().classes('bg-[#1e1f20] border border-white/10 p-6 w-96'):
                                                    ui.label('Clear Logs?').classes('text-xl font-bold text-gray-200 mb-2')
                                                    ui.label('Are you sure you want to clear all logs from llm_debug.log? This cannot be undone.').classes('text-gray-400 text-sm mb-6')

                                                    with ui.row().classes('w-full justify-end gap-2'):
                                                        def _confirm_clear():
                                                            confirm_dialog.close()
                                                            import os
                                                            log_path = os.path.join(os.getcwd(), 'logs', 'llm_debug.log')
                                                            try:
                                                                if os.path.exists(log_path):
                                                                    with open(log_path, 'w', encoding='utf-8') as f:
                                                                        f.truncate(0)
                                                                    log_label.set_text("Log file is empty.")
                                                                    ui.notify('Logs cleared successfully', type='positive')
                                                                else:
                                                                    ui.notify('Log file is already empty or does not exist', type='info')
                                                            except Exception as ex:
                                                                ui.notify(f'Failed to clear logs: {ex}', type='negative')

                                                        ui.button('Cancel', on_click=confirm_dialog.close).props('flat color=grey')
                                                        ui.button('Clear', on_click=_confirm_clear).props('flat color=red')
                                                confirm_dialog.open()
                                            
                                            ui.button(icon='delete_forever', on_click=_clear_logs_from_popup).props('flat round color=red').tooltip('Clear Logs')
                                            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey').tooltip('Close')
                                    
                                    with ui.element('div').classes('w-full flex-grow bg-[#0c0c0c] border border-white/10 rounded-lg p-3 overflow-auto'):
                                        log_label = ui.label().classes('text-gray-300 font-mono text-xs whitespace-pre')
                                
                                async def _load_logs():
                                    log_label.set_text("Loading logs...")
                                    try:
                                        import os
                                        log_path = os.path.join(os.getcwd(), 'logs', 'llm_debug.log')
                                        if not os.path.exists(log_path):
                                            log_label.set_text("Log file does not exist.")
                                            return
                                        
                                        def read_file():
                                            file_size = os.path.getsize(log_path)
                                            max_bytes = 150 * 1024  # last 150KB
                                            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                                                if file_size > max_bytes:
                                                    f.seek(file_size - max_bytes)
                                                    f.readline()  # skip partial line
                                                return f.read()
                                        
                                        content = await run.io_bound(read_file)
                                        if not content.strip():
                                            log_label.set_text("Log file is empty.")
                                            return
                                        
                                        log_label.set_text(content)
                                    except Exception as ex:
                                        log_label.set_text(f"Error loading logs: {ex}")
                                
                                async def _copy_logs():
                                    try:
                                        import os
                                        log_path = os.path.join(os.getcwd(), 'logs', 'llm_debug.log')
                                        if not os.path.exists(log_path):
                                            ui.notify("Log file does not exist.", type='warning')
                                            return
                                        
                                        def read_file():
                                            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                                                return f.read()
                                        
                                        content = await run.io_bound(read_file)
                                        if not content.strip():
                                            ui.notify("Log file is empty.", type='warning')
                                            return
                                        
                                        import json
                                        escaped = json.dumps(content)
                                        await ui.run_javascript(f"navigator.clipboard.writeText({escaped})")
                                        ui.notify("Logs copied to clipboard", type='positive')
                                    except Exception as ex:
                                        ui.notify(f"Failed to copy logs: {ex}", type='negative')

                            dialog.open()
                            asyncio.create_task(_load_logs())

                        def _clear_logs():
                            with ui.dialog() as dialog, ui.card().classes('bg-[#1e1f20] border border-white/10 p-6 w-96'):
                                ui.label('Clear Logs?').classes('text-xl font-bold text-gray-200 mb-2')
                                ui.label('Are you sure you want to clear all logs from llm_debug.log? This cannot be undone.').classes('text-gray-400 text-sm mb-6')

                                with ui.row().classes('w-full justify-end gap-2'):
                                    def _confirm_clear():
                                        dialog.close()
                                        import os
                                        log_path = os.path.join(os.getcwd(), 'logs', 'llm_debug.log')
                                        try:
                                            if os.path.exists(log_path):
                                                with open(log_path, 'w', encoding='utf-8') as f:
                                                    f.truncate(0)
                                                ui.notify('Logs cleared successfully', type='positive')
                                            else:
                                                ui.notify('Log file is already empty or does not exist', type='info')
                                        except Exception as ex:
                                            ui.notify(f'Failed to clear logs: {ex}', type='negative')

                                    ui.button('Cancel', on_click=dialog.close).props('flat color=grey')
                                    ui.button('Clear', on_click=_confirm_clear).props('flat color=red')
                            dialog.open()

                        ui.link('Show Logs', 'javascript:void(0)').classes(
                            'text-indigo-400 hover:text-indigo-300 underline text-xs font-semibold cursor-pointer transition-colors'
                        ).on('click', _show_logs)

                        ui.link('Clear Logs', 'javascript:void(0)').classes(
                            'text-red-400 hover:text-red-300 underline text-xs font-semibold cursor-pointer transition-colors'
                        ).on('click', _clear_logs)

            with ui_card(
                heading="Logging Configuration",
                heading_icon="article",
                heading_color="indigo",
                footer=_logging_footer,
            ):
                with ui.column().classes('gap-4'):
                    ui.checkbox('Enable Chat Logging',
                                value=config_manager.is_logging_enabled('chat'),
                                on_change=lambda e: config_manager.set_logging('chat', e.value)).classes('text-gray-300')

                    ui.checkbox('Enable Batch Logging',
                                value=config_manager.is_logging_enabled('batch'),
                                on_change=lambda e: config_manager.set_logging('batch', e.value)).classes('text-gray-300')

            # ── Rating Tags ───────────────────────────────────────────────────
            with ui_card(heading="Rating Tags", heading_icon="label", heading_color="purple"):
                tags_container = ui.row().classes('gap-2 mb-4')

                def render_tags():
                    tags_container.clear()
                    with tags_container:
                        for tag in config_manager.get_rating_tags():
                            c = ui.chip(removable=True, icon='label', color='indigo-9')
                            c.classes('text-indigo-200')
                            c.on('remove', lambda _, t=tag: remove_tag(t))
                            with c:
                                ui.label(tag)

                def add_tag():
                    new_tag = tag_input.value.strip()
                    if new_tag:
                        config_manager.add_rating_tag(new_tag)
                        tag_input.value = ''
                        render_tags()

                def remove_tag(tag):
                    config_manager.remove_rating_tag(tag)
                    render_tags()

                with ui.row().classes('items-center gap-2'):
                    tag_input = ui.input(placeholder='New Tag Name').classes('w-64').on('keydown.enter', add_tag)
                    ui.button(icon='add', on_click=add_tag).props('flat round color=secondary')

                render_tags()

            # ── Note Categories ───────────────────────────────────────────────
            with ui_card(heading="Note Categories", heading_icon="folder", heading_color="emerald"):
                cats_container = ui.row().classes('gap-2 mb-4')

                def render_cats():
                    cats_container.clear()
                    with cats_container:
                        for cat in config_manager.get_note_categories():
                            c = ui.chip(removable=True, icon='folder', color='emerald-9')
                            c.classes('text-emerald-200')
                            c.on('remove', lambda _, t=cat: remove_cat(t))
                            with c:
                                ui.label(cat)

                def add_cat():
                    new_cat = cat_input.value.strip()
                    if new_cat:
                        config_manager.add_note_category(new_cat)
                        cat_input.value = ''
                        render_cats()

                def remove_cat(cat):
                    config_manager.remove_note_category(cat)
                    render_cats()

                with ui.row().classes('items-center gap-2'):
                    cat_input = ui.input(placeholder='New Category').classes('w-64').on('keydown.enter', add_cat)
                    ui.button(icon='add', on_click=add_cat).props('flat round color=secondary')

                render_cats()

                ui.separator().classes('my-4 bg-white/10')
                ui.label('Storage Location').classes('text-sm font-bold text-gray-400 mb-2')

                def handle_storage_change(e):
                    new_val = e.value
                    old_val = config_manager.get_note_storage()

                    if new_val == old_val:
                        return

                    with ui.dialog() as dialog, ui.card().classes('bg-[#1e1f20] border border-white/10 p-6 w-96'):
                        ui.label('Sync Notes?').classes('text-xl font-bold text-gray-200 mb-2')
                        ui.label('Merge existing notes from both locations?').classes('text-gray-400 text-sm mb-6')

                        with ui.row().classes('w-full justify-end gap-2'):
                            async def do_sync():
                                dialog.close()
                                ui.notify('Syncing...', type='info')
                                try:
                                    from nicegui import run as ng_run
                                    count = await ng_run.io_bound(note_service.sync_notes)
                                    config_manager.set_note_storage(new_val)
                                    ui.notify(f'Synced {count} notes using {new_val}', type='positive')
                                except Exception as ex:
                                    ui.notify(f'Sync failed: {ex}', type='negative')
                                    storage_select.value = old_val

                            def just_switch():
                                dialog.close()
                                config_manager.set_note_storage(new_val)
                                ui.notify(f'Switched to {new_val}', type='positive')

                            def cancel():
                                dialog.close()
                                storage_select.value = old_val

                            ui.button('Cancel', on_click=cancel).props('flat color=grey')
                            ui.button('Switch Only', on_click=just_switch).props('flat color=warning')
                            ui.button('Sync & Switch', on_click=do_sync).props('flat color=primary')

                    dialog.open()

                storage_select = ui.select(
                    ['local', 'google_drive'],
                    label='Save Notes To',
                    value=config_manager.get_note_storage(),
                    on_change=handle_storage_change,
                ).classes('w-full')

            # ── Default Persona ───────────────────────────────────────────────
            with ui_card(heading="Default Persona", heading_icon="person", heading_color="purple"):
                ui.label(
                    'This persona\'s system prompt will be pre-filled in new chat sessions.'
                ).classes('text-sm text-gray-500 mb-2')

                def _persona_options():
                    opts = persona_service.get_all_persona_options()
                    return {p['id']: p['name'] for p in opts}

                def _on_default_persona_change(e):
                    persona_service.set_default_persona_id(e.value)
                    ui.notify('Default persona saved', type='positive')

                default_persona_select = ui.select(
                    options=_persona_options(),
                    label='Default Persona',
                    value=persona_service.get_default_persona_id(),
                    on_change=_on_default_persona_change,
                ).classes('w-full').props('outlined dense dark')

                def _refresh_persona_opts():
                    default_persona_select.options = _persona_options()
                    # Make sure current value is still valid
                    if default_persona_select.value not in default_persona_select.options:
                        default_persona_select.value = persona_service.get_default_persona_id()

                # Refresh options lazily so newly-created personas appear
                ui.timer(2.0, _refresh_persona_opts)

            # ── Default Models ────────────────────────────────────────────────
            with ui_card(heading="Default Models", heading_icon="psychology", heading_color="indigo"):
                async def load_models_for_setting():
                    from utils.llm_client import client
                    try:
                        models_list = await client.list_models()
                        options = [m['model'] for m in models_list]
                        story_model_select.options = options
                        
                        # Load from config
                        current = config_manager.get_default_model('story_processing')
                        if current in options:
                            story_model_select.value = current
                        elif options:
                            story_model_select.value = options[0]
                    except Exception:
                        pass

                story_model_select = ui.select(
                    options=[], 
                    label='Story Processing Model',
                    on_change=lambda e: config_manager.set_default_model('story_processing', e.value)
                ).classes('w-full')
                ui.timer(0.1, load_models_for_setting, once=True)

            # ── Audio ─────────────────────────────────────────────────────────
            with ui_card(heading="Audio Settings", heading_icon="volume_up", heading_color="pink"):
                with ui.column().classes('gap-4 w-full'):
                    with ui.column().classes('gap-1 w-full'):
                        ui.label('Chat Audio Voice').classes('text-sm font-bold text-gray-400')
                        with ui.row().classes('items-center gap-2 w-full'):
                            voice_select = ui.select(
                                options=VOICES,
                                value=config_manager.get_tts_voice(),
                                on_change=lambda e: config_manager.set_tts_voice(e.value)
                            ).classes('flex-1').props('outlined dense dark')

                            _SAMPLE_TEXT = "Hello! This is a preview of the selected voice."

                            async def _play_voice_sample(btn=None):
                                selected_voice = voice_select.value or config_manager.get_tts_voice()
                                if not selected_voice:
                                    ui.notify('No voice selected', type='warning')
                                    return
                                if btn:
                                    btn.props('loading')
                                try:
                                    b64_list = await asyncio.to_thread(
                                        tts_service.generate_audio_b64, _SAMPLE_TEXT, selected_voice
                                    )
                                    if not b64_list:
                                        ui.notify('TTS not available', type='negative')
                                        return
                                    # Initialise the JS audio queue if needed and play
                                    await ui.run_javascript("""
                                        if (!window.audioQueue) {
                                            window.audioQueue = [];
                                            window.isPlayingAudio = false;
                                            window.currentAudioObj = null;
                                            window.stopAudio = function() {
                                                window.audioQueue = [];
                                                if (window.currentAudioObj) {
                                                    window.currentAudioObj.pause();
                                                    window.currentAudioObj = null;
                                                }
                                                window.isPlayingAudio = false;
                                            };
                                            window.playNextAudio = function() {
                                                if (window.audioQueue.length > 0 && !window.isPlayingAudio) {
                                                    window.isPlayingAudio = true;
                                                    let src = window.audioQueue.shift();
                                                    window.currentAudioObj = new Audio('data:audio/wav;base64,' + src);
                                                    window.currentAudioObj.onended = function() {
                                                        window.isPlayingAudio = false;
                                                        window.playNextAudio();
                                                    };
                                                    window.currentAudioObj.play().catch(e => {
                                                        console.error('Audio play error', e);
                                                        window.isPlayingAudio = false;
                                                        window.playNextAudio();
                                                    });
                                                }
                                            };
                                        } else {
                                            if (window.stopAudio) window.stopAudio();
                                        }
                                    """)
                                    for b64 in b64_list:
                                        await ui.run_javascript(
                                            f"window.audioQueue.push('{b64}'); window.playNextAudio();"
                                        )
                                except Exception as ex:
                                    ui.notify(f'Preview error: {ex}', type='negative')
                                finally:
                                    if btn:
                                        btn.props(remove='loading')

                            preview_btn = ui.button(
                                icon='play_arrow',
                                on_click=lambda: _play_voice_sample(preview_btn),
                            ).props('flat round color=pink').tooltip('Preview voice')

            # ── Visual ────────────────────────────────────────────────────────
            with ui_card(heading="Visual Settings", heading_icon="image", heading_color="indigo"):
                ui.checkbox('Show Hidden').bind_value(
                    app.storage.user, 'visual_show_hidden'
                ).classes('text-gray-300').tooltip('Show hidden images in the history grid')

