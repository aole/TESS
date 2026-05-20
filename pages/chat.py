from nicegui import ui, app
from utils.llm_client import client
from utils.config import config_manager
from services.tool_service import tool_service
from services.rating_service import rating_service
from services.chat_service import chat_service
from utils.chat_renderer import ConversationRenderer
from services.stream_service import stream_service
from services.batch_service import batch_service
from services.tts_service import tts_service
from utils.ui_components import ui_list, ui_list_item
from utils.audio_player import AudioPlayer
from utils.settings_dialog import SettingsDialog
from services.persona_service import persona_service, NO_PERSONA_ID
import asyncio
import uuid

async def create_page(model_param: str = None, new_chat: bool = False):
    # Use the passed parameter
    query_model = model_param
    # State
    page_client = ui.context.client

    def _get_most_recent_empty_chat():
        """Return the most recently updated chat if it has no messages; otherwise None."""
        try:
            chats = chat_service.list_chats()
            if not chats:
                return None
            last = chats[0]
            chat = chat_service.load_chat(last.get('id'))
            if chat and not chat.messages:
                return chat
        except Exception:
            pass
        return None

    def _create_or_reuse_empty_chat(title: str = "New Chat"):
        """Avoid creating duplicate empty chats when the last chat is already empty."""
        chat = _get_most_recent_empty_chat()
        if chat:
            return chat
        return chat_service.create_chat(title=title)

    if new_chat:
        # If the most recent chat is empty, reuse it instead of creating another empty chat.
        chat = _create_or_reuse_empty_chat(title="New Chat")
        app.storage.user['chat_id'] = chat.id
        app.storage.user['messages'] = []
        
        # Clean up URL (optional but recommended to avoid re-creation on refresh)
        from urllib.parse import quote
        safe_model = quote(model_param) if model_param else ""
        url = f"/chat?model={safe_model}" if safe_model else "/chat"
        await ui.run_javascript(f"window.history.replaceState(null, '', '{url}');")

    if 'messages' not in app.storage.user:
        app.storage.user['messages'] = []
    if 'chat_id' not in app.storage.user:
        app.storage.user['chat_id'] = None
    # Clear unlocked chats when the page is newly loaded
    app.storage.user['unlocked_chats'] = {}

    # We use lists/dicts in storage, distinct from the local variables
    # We reference them here, but we must be careful to update the storage when we change them.
    # To simplify, we will update app.storage.user['messages'] explicitly.
    
    messages = app.storage.user['messages']
    current_chat_id = app.storage.user['chat_id'] 

    # Re-sync from disk to ensure storage is consistent with persistent file
    if current_chat_id:
        chat = chat_service.load_chat(current_chat_id)
        if chat:
            if chat.is_encrypted:
                pw = app.storage.user['unlocked_chats'].get(current_chat_id)
                if pw and chat_service.verify_password(current_chat_id, pw):
                    messages = chat_service.decrypt_messages(chat.messages, pw, chat.salt)
                else:
                    messages = chat.messages
            else:
                messages = chat.messages
            # Update storage with fresh data from disk
            app.storage.user['messages'] = messages
        else:
            # Chat ID exists in session but file missing? Reset.
            current_chat_id = None
            app.storage.user['chat_id'] = None
            messages = []
            app.storage.user['messages'] = messages 

    # Ensure all messages have IDs
    for msg in messages:
        if 'id' not in msg:
            msg['id'] = str(uuid.uuid4())
    
    state = {'processing': False, 'stopping': False, 'last_update_msg_id': None, 'has_attachments': False}
    
    # Initialize Audio Player
    audio_player = AudioPlayer(
        page_client=page_client,
        on_state_change=lambda: chat_renderer.render_messages(messages)
    )

    # Model Selection Logic (Prep)
    try:
        models_data = await client.list_models()
        model_options = [m['model'] for m in models_data]
    except Exception as e:
        model_options = []
        ui.notify(f"Error loading models: {e}", type='negative')

    # Use query param model if available and valid, otherwise fallback to storage
    default_model = model_options[0] if model_options else None
    if query_model and query_model in model_options:
        default_model = query_model
    elif app.storage.user.get('selected_model') in model_options:
        default_model = app.storage.user['selected_model']

    # --- Persistance Helper ---
    async def save_current_chat():
        nonlocal current_chat_id
        if not messages: 
            return # Don't save empty chats unless they already exist? 
                   # Actually, if we just created a "New Chat" and haven't typed, we might not want to save it yet.
        
        with page_client:
            try:
                # Determine title if new
                title = "New Chat"
                if messages:
                    # Find first user message
                    for m in messages:
                        if m['role'] == 'user':
                            title = m['content'][:40] + "..." if len(m['content']) > 40 else m['content']
                            break
                
                if current_chat_id:
                    # Update existing
                    chat = chat_service.load_chat(current_chat_id)
                    if chat:
                        chat.title = title 
                        
                        # Update title if it was default
                        if chat.title == "New Chat" and title != "New Chat":
                            chat.title = title

                        if chat.is_encrypted:
                            pw = app.storage.user['unlocked_chats'].get(current_chat_id)
                            if pw:
                                chat.messages = chat_service.encrypt_messages(messages, pw, chat.salt)
                            else:
                                chat.messages = messages
                        else:
                            chat.messages = messages
                        
                        chat_service.save_chat(chat)
                else:
                    # Create new
                    chat = chat_service.create_chat(title=title)
                    chat.messages = messages
                    chat_service.save_chat(chat)
                    current_chat_id = chat.id
                    app.storage.user['chat_id'] = current_chat_id
                
                # Refresh list
                refresh_chat_list()
            except Exception as e:
                ui.notify(f"Error saving chat: {e}", type='negative')

    # --- Sidebar & Navigation ---
    drawer = ui.left_drawer(value=True).classes('bg-[#18181b] border-r border-white/10 flex flex-col flex-nowrap')
    with drawer:
        with ui.column().classes('w-full p-4 gap-1 shrink-0 border-b border-white/5'):
            ui.label('Model').classes('text-sm font-medium text-gray-400 mb-1')
            model_select = ui.select(options=model_options, value=default_model).props('dense options-dense outlined dark').classes('w-full text-sm mb-2')
            model_select.on_value_change(lambda e: update_params())

            # ── Persona picker ────────────────────────────────────────────────
            ui.label('Persona').classes('text-sm font-medium text-gray-400 mb-1')

            def _build_persona_opts():
                opts = persona_service.get_all_persona_options()
                return {p['id']: p['name'] for p in opts}

            # Determine initial persona selection
            _saved_prompt = app.storage.user.get('system_prompt')
            _default_persona = persona_service.get_default_persona()
            _initial_persona_id = app.storage.user.get(
                'selected_persona_id',
                _default_persona['id'],
            )
            # Pre-fill system prompt from default persona if none saved yet
            if _saved_prompt is None:
                app.storage.user['system_prompt'] = _default_persona['system_prompt']

            def _on_persona_change(e):
                pid = e.value
                app.storage.user['selected_persona_id'] = pid
                persona = persona_service.get_persona(pid)
                if persona is not None:
                    system_prompt.value = persona['system_prompt']
                    app.storage.user['system_prompt'] = persona['system_prompt']

            persona_select = ui.select(
                options=_build_persona_opts(),
                value=_initial_persona_id,
                on_change=_on_persona_change,
            ).props('dense options-dense outlined dark').classes('w-full text-sm mb-2')

            # Refresh persona options periodically (picks up newly created personas)
            def _refresh_persona_opts():
                persona_select.options = _build_persona_opts()

            ui.timer(3.0, _refresh_persona_opts)

            # ── System Prompt ─────────────────────────────────────────────────
            ui.label('System Prompt').classes('text-sm font-medium text-gray-400 mb-1')
            system_prompt = ui.textarea(
                placeholder='You are a helpful assistant...', 
                value=app.storage.user.get('system_prompt', '')
            ).props('dense rows=4 filled flat').classes('w-full text-sm mb-2 bg-white/5 rounded-md').on('blur', lambda e: app.storage.user.update({'system_prompt': e.sender.value}))

        with ui.column().classes('w-full flex-grow min-h-0'):
            chat_list_container = ui_list(
                heading='History',
                action_icon='add',
                action_tooltip='New Chat',
                on_action=lambda: load_new_chat(),
            )

    def load_new_chat():
        nonlocal messages, current_chat_id
        
        if current_chat_id:
            app.storage.user['unlocked_chats'].pop(current_chat_id, None)

        # If the most recent chat is empty, reuse it instead of creating another empty chat.
        chat = _create_or_reuse_empty_chat(title="New Chat")
        current_chat_id = chat.id
        messages = []
        
        app.storage.user['messages'] = messages
        app.storage.user['chat_id'] = current_chat_id
        
        refresh_chat_ui()
        refresh_chat_list()
        try:
            update_encryption_ui()
        except NameError: pass
        # Optionally close drawer on mobile?
    
    def load_chat_by_id(chat_id):
        nonlocal messages, current_chat_id
        if current_chat_id and current_chat_id != chat_id:
            app.storage.user['unlocked_chats'].pop(current_chat_id, None)
        chat = chat_service.load_chat(chat_id)
        if chat:
            current_chat_id = chat.id
            if chat.is_encrypted:
                pw = app.storage.user['unlocked_chats'].get(chat_id)
                if pw and chat_service.verify_password(chat_id, pw):
                    messages = chat_service.decrypt_messages(chat.messages, pw, chat.salt)
                else:
                    messages = chat.messages
            else:
                messages = chat.messages
            app.storage.user['messages'] = messages
            app.storage.user['chat_id'] = current_chat_id
            if 'refresh_chat_ui' in locals():
                refresh_chat_ui()
            refresh_chat_list()
            try:
                update_encryption_ui()
            except NameError: pass
        else:
            ui.notify("Could not load chat", type='negative')

    def delete_chat_history(chat_id):
        chat_service.delete_chat(chat_id)
        if current_chat_id == chat_id:
            chats = chat_service.list_chats()
            if chats:
                load_chat_by_id(chats[0]['id'])
            else:
                load_new_chat()
        else:
            refresh_chat_list()

    def refresh_chat_list():
        chat_list_container.clear()
        chats = chat_service.list_chats()
        with chat_list_container:
            if not chats:
                ui.label('No history').classes('text-sm text-gray-500 italic p-4')

            for c in chats:
                is_active = c['id'] == current_chat_id
                with ui_list_item(
                    title=c['title'],
                    subtitle=c['updated_at'][:10],
                    subtitle_icon='lock' if c.get('is_encrypted') else None,
                    active=is_active,
                    on_click=lambda cid=c['id']: load_chat_by_id(cid),
                    action_icon='delete',
                    action_color='red-4',
                    action_tooltip='Delete chat',
                    on_action=lambda cid=c['id']: delete_chat_history(cid),
                ):
                    pass

    # Initial Refresh
    refresh_chat_list()

    # Helper to load tool code
    def load_tool_function(name: str, code: str):
        try:
            scope = {}
            exec(code, scope)
            if name in scope and callable(scope[name]):
                return scope[name]
        except Exception as e:
            print(f"Error loading tool code: {e}")
        return None
    
    # Settings Dialog
    def clear_chat():
        messages.clear()
        app.storage.user['messages'] = []
        refresh_chat_ui()
        settings_dialog.close()

    settings_dialog = SettingsDialog(
        model_options=model_options,
        on_clear_chat=clear_chat,
        on_chat_updated=lambda chat_id=None: load_chat_by_id(chat_id) if chat_id else refresh_chat_ui(),
        get_current_chat_id=lambda: current_chat_id,
        get_messages=lambda: messages,
        model_select_component=model_select
    )

    # Parameter update logic
    async def update_params(initial=False):
        if not model_select.value: return
        
        # Update storage
        app.storage.user['selected_model'] = model_select.value

        with model_select:
            # Update URL without reload
            from urllib.parse import quote
            safe_model = quote(model_select.value)
            await ui.run_javascript(f"window.history.replaceState(null, '', '/chat?model={safe_model}');")

            # Check if there is a custom model configuration
            model_configs = app.storage.general.get('model_configurations', {})
            model_cfg = model_configs.get(model_select.value)
            if model_cfg:
                # Apply system prompt / persona
                persona_id = model_cfg.get('persona_id', NO_PERSONA_ID)
                app.storage.user['selected_persona_id'] = persona_id
                
                if persona_id != NO_PERSONA_ID:
                    persona = persona_service.get_persona(persona_id)
                    if persona:
                        app.storage.user['system_prompt'] = persona['system_prompt']
                    else:
                        app.storage.user['system_prompt'] = model_cfg.get('system_prompt', '')
                else:
                    app.storage.user['system_prompt'] = model_cfg.get('system_prompt', '')

                # Tools configuration
                tools_enabled = model_cfg.get('tools_enabled', True)
                app.storage.user['tools_enabled'] = tools_enabled
                if 'models_without_tools' not in app.storage.general:
                    app.storage.general['models_without_tools'] = []

                if not tools_enabled:
                    if model_select.value not in app.storage.general['models_without_tools']:
                        app.storage.general['models_without_tools'].append(model_select.value)
                    app.storage.user['web_search_enabled'] = False
                    app.storage.user['visual_enabled'] = False
                    app.storage.user['memory_enabled'] = False
                else:
                    if model_select.value in app.storage.general['models_without_tools']:
                        app.storage.general['models_without_tools'].remove(model_select.value)

                # Memory configuration
                if tools_enabled:
                    app.storage.user['memory_enabled'] = model_cfg.get('memory_enabled', True)

                # Sync UI components
                try:
                    system_prompt.value = app.storage.user.get('system_prompt', '')
                except:
                    pass
                try:
                    persona_select.value = app.storage.user.get('selected_persona_id', NO_PERSONA_ID)
                except:
                    pass

                # Call the UI updater if defined
                if 'update_tool_buttons' in locals():
                    try:
                        update_tool_buttons()
                    except Exception:
                        pass
                return

            # If this is the initial load and we have saved settings, don't overwrite them with model defaults
            has_saved = any(k in app.storage.user for k in ['system_prompt'])
            if initial and has_saved and app.storage.user.get('system_prompt'):
                return

            new_params = await client.get_model_parameters(model_select.value)
            
            if 'system' in new_params:
                app.storage.user['system_prompt'] = new_params['system']
            
            # Sync side prompt if needed
            system_prompt.value = app.storage.user.get('system_prompt', '')


    # Layout (just chat area now)
    with ui.row().classes('w-full max-w-[1200px] mx-auto h-[calc(100vh-3rem)] pt-4 px-4 items-stretch flex-nowrap'):
        # --- Right Area (Chat) ---
        with ui.column().classes('flex-grow h-full gap-1 relative min-w-0'):
            chat_container = ui.column().classes('w-full flex-grow overflow-y-auto p-4 gap-4 rounded-lg bg-black/20 border border-white/5').props('id=chat-scroll-area')
            
            async def scroll_to_bottom(check_position=False):
                with chat_container:
                    js = """
                    var el = document.getElementById("chat-scroll-area");
                    if (el) {
                        if (typeof window.isChatAtBottom === 'undefined') {
                            window.isChatAtBottom = true;
                        }
                        if (!el.dataset.hasScrollListener) {
                            el.dataset.hasScrollListener = "true";
                            el.addEventListener('scroll', function() {
                                    window.isChatAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < 50;
                            });
                        }
                        if (!CHECK_POSITION) {
                            el.scrollTop = el.scrollHeight;
                            window.isChatAtBottom = true;
                        } else if (window.isChatAtBottom) {
                                el.scrollTop = el.scrollHeight;
                        }
                    }
                    """.replace('CHECK_POSITION', 'true' if check_position else 'false')
                    await ui.run_javascript(js)

            # Logic Handlers (Wrappers for Renderer)
            def handle_delete(msg):
                indices_to_remove = ConversationRenderer.get_turn_indices(messages, msg)
                if not indices_to_remove:
                    return
                
                # Apply deletion
                new_messages = [m for i, m in enumerate(messages) if i not in indices_to_remove]
                messages[:] = new_messages
                
                app.storage.user['messages'] = messages
                chat_renderer.render_messages(messages)
                asyncio.create_task(save_current_chat())

            def handle_edit(msg):
                # Reset others
                for m in messages:
                    m['editing'] = False
                msg['editing'] = True
                chat_renderer.render_messages(messages)

            def handle_cancel_edit(msg):
                msg['editing'] = False
                chat_renderer.render_messages(messages)
            
            def handle_save_edit(msg, new_content):
                msg['content'] = new_content
                msg['editing'] = False
                app.storage.user['messages'] = messages
                chat_renderer.render_messages(messages)
                asyncio.create_task(save_current_chat())

            async def handle_rate(msg, rating, tag):
                if not msg.get('id'): return
                rating_service.add_rating(
                    model=msg.get('model', 'unknown'),
                    tag=tag,
                    rating=rating,
                    message_id=msg['id']
                )
                ui.notify(f"Rated {rating} stars for {tag}", type='positive')
                chat_renderer.render_messages(messages)

            async def handle_delete_rating(msg, tag):
                if not msg.get('id'): return
                rating_service.remove_rating(msg['id'], tag)
                ui.notify(f"Removed rating for {tag}", type='info')
                chat_renderer.render_messages(messages)
                
            def get_msg_ratings(msg_id):
                return rating_service.get_ratings_for_message(msg_id)

            # --- Instantiate Renderer ---
            chat_renderer = ConversationRenderer(
                container=chat_container,
                on_edit=handle_edit,
                on_save_edit=handle_save_edit,
                on_cancel_edit=handle_cancel_edit,
                on_delete=handle_delete,
                on_rate=handle_rate,
                on_delete_rating=handle_delete_rating,
                on_play_tts=lambda msg: asyncio.create_task(audio_player.play_message(msg)),
                get_playing_tts_id=lambda: audio_player.playing_tts_id,
                get_ratings=get_msg_ratings,
                available_tags=config_manager.get_rating_tags(),
                on_save_and_respond=None # Will be set later
            )
            ui.timer(1.0, audio_player.sync_tts_state)
            
            async def on_stream_event(event_type, *args):
                with page_client:
                    if event_type == 'new_message':
                        msg = args[0]
                        # Update local messages list if not present (data sync)
                        if not any(m.get('id') == msg['id'] for m in messages):
                            messages.append(msg)
                            try:
                                app.storage.user['messages'] = messages
                            except: pass
                        
                        # Render if not already rendered (UI sync)
                        if msg['id'] not in chat_renderer._msg_elements:
                            with chat_container:
                                chat_renderer.render_message(msg)
                            await scroll_to_bottom()
                            
                    elif event_type == 'update_message':
                        msg_id, content, thinking, tool_calls = args
                        await chat_renderer.update_message(msg_id, content, thinking, tool_calls)
                        await scroll_to_bottom(check_position=True)
                        
                        state['last_update_msg_id'] = msg_id
                        if config_manager.is_tts_enabled():
                            await audio_player.process_stream_chunk(msg_id, content)
                                
                    elif event_type == 'done':
                        state['processing'] = False
                        state['stopping'] = False
                        update_button_state()
                        
                        # handle trailing text for TTS
                        last_id = state.get('last_update_msg_id')
                        if last_id and config_manager.is_tts_enabled():
                            for m in messages:
                                if m.get('id') == last_id:
                                    await audio_player.process_stream_chunk(last_id, m.get('content', ''), is_done=True)
                                    break
                                    
                        # Refresh to ensure consistency
                        try:
                            app.storage.user['messages'] = messages
                        except: pass
                    elif event_type == 'error':
                        ui.notify(f"Stream error: {args[0]}", type='negative')
                        state['processing'] = False
                        update_button_state()


            
            def refresh_chat_ui():
                chat_renderer.render_messages(messages)

            # Scroll init
            if messages:
                refresh_chat_ui()
                await scroll_to_bottom()

            # Encryption Controls
            encryption_controls = ui.row().classes('w-full items-center justify-end gap-2 px-2 pb-2')
            
            # Encryption UI is now handled by settings_dialog for the buttons there.
            # We still need a way to disable input if locked.

            # --- Input Area ---
            with ui.column().classes('w-full gap-1 p-2 glass-panel rounded-lg'):
                user_input = ui.textarea(placeholder='Type a message...').classes('w-full flex-grow').props('autogrow bg-color=transparent borderless dense rows=1')
                
                # Forward declaration for button
                send_btn = None
                attached_files = []

                def open_settings():
                    settings_dialog.open()

                # --- File Attachment Logic ---
                async def handle_upload(e):
                    try:
                        content_bytes = await e.file.read()
                        content = content_bytes.decode('utf-8')
                        attached_files.append({'name': e.file.name, 'content': content})
                        ui.notify(f'Attached {e.file.name}', type='positive')
                        refresh_attachments_ui()
                    except Exception as ex:
                        filename = getattr(getattr(e, 'file', None), 'name', 'Unknown file')
                        ui.notify(f'Error reading {filename}: {ex}', type='negative')

                def remove_attachment(index):
                    if 0 <= index < len(attached_files):
                        attached_files.pop(index)
                        refresh_attachments_ui()

                def refresh_attachments_ui():
                    attachment_container.clear()
                    with attachment_container:
                        for i, f in enumerate(attached_files):
                            with ui.badge(f.get('name', 'Unknown'), color='blue-6').classes('cursor-pointer px-2 py-1 items-center'):
                                ui.label(f.get('name', 'Unknown'))
                                ui.icon('close', size='12px').classes('ml-1').on('click', lambda i=i: remove_attachment(i))

                attachment_container = ui.row().classes('w-full gap-2 px-2 pb-1')
                uploader = ui.upload(on_upload=handle_upload, multiple=True, auto_upload=True).props('accept=".txt,.md,.csv,.py,.js,.json,.html,.css,.sql,.yaml,.yml"').classes('hidden')

                def update_button_state():
                    if not send_btn: return
                    is_streaming = stream_service.any_active() or batch_service.any_active()
                    if state['processing'] or is_streaming:
                        if state['stopping']:
                            send_btn.props('icon=hourglass_empty color=warning')
                        else:
                            send_btn.props('icon=stop color=negative')
                    else:
                        send_btn.props('icon=send color=primary')
                
                ui.timer(1.0, update_button_state)

                def is_chat_locked():
                    if not current_chat_id: return False
                    chat = chat_service.load_chat(current_chat_id)
                    if not chat or not chat.is_encrypted: return False
                    pw = app.storage.user.get('unlocked_chats', {}).get(current_chat_id)
                    return not (pw and chat_service.verify_password(current_chat_id, pw))

                def update_encryption_ui():
                    if is_chat_locked():
                        if 'user_input' in locals() and user_input:
                            user_input.props('disable=true')
                            user_input.placeholder = 'Chat is locked. Unlock in settings to continue.'
                            if send_btn: send_btn.props('disable=true')
                    else:
                        if 'user_input' in locals() and user_input:
                            user_input.props('disable=false')
                            user_input.placeholder = 'Type a message...'
                            if send_btn: send_btn.props('disable=false')

                update_encryption_ui()
                ui.timer(2.0, update_encryption_ui)

                # --- Core Generation Logic ---
                async def generate_response():
                    if is_chat_locked():
                        ui.notify("Chat is locked.", type='warning')
                        return
                    if state['processing'] and not state['stopping']:
                         return
                    state['processing'] = True
                    state['stopping'] = False
                    update_button_state()

                    tools_enabled = app.storage.user.get('tools_enabled', True)
                    tool_funcs_map = {}

                    if tools_enabled:
                        available_tools = [t for t in tool_service.get_all_tools() if t.active]

                        for t in available_tools:
                            if not t.is_builtin:
                                func = load_tool_function(t.name, t.code)
                                if func: tool_funcs_map[func.__name__] = func

                        if app.storage.user.get('web_search_enabled', False) and config_manager.is_tool_active('web_search_tool'):
                            try:
                                from utils.web_search_tool import web_search, extract_url
                                tool_funcs_map['web_search'] = web_search
                                tool_funcs_map['extract_url'] = extract_url
                            except ImportError: pass

                        if app.storage.user.get('visual_enabled', False) and config_manager.is_tool_active('visual_tool'):
                            try:
                                from utils.visual_tool import generate_image
                                tool_funcs_map['generate_image'] = generate_image
                            except ImportError: pass

                        if app.storage.user.get('memory_enabled', True) and config_manager.is_tool_active('user_memory_tool'):
                            try:
                                from utils.memory_tool import update_user_info, get_user_info, delete_user_info
                                tool_funcs_map['update_user_info'] = update_user_info
                                tool_funcs_map['get_user_info'] = get_user_info
                                tool_funcs_map['delete_user_info'] = delete_user_info
                            except ImportError: pass
                    
                    if not current_chat_id: await save_current_chat()
                    
                    if current_chat_id:
                        stream_service.register_listener(current_chat_id, on_stream_event)
                        async def persist_chat(updated_messages):
                            if current_chat_id:
                                chat = chat_service.load_chat(current_chat_id)
                                if chat:
                                    chat.messages = updated_messages
                                    chat_service.save_chat(chat)

                        memory_enabled = bool(tools_enabled and app.storage.user.get('memory_enabled', True) and config_manager.is_tool_active('user_memory_tool'))
                        has_attachments = bool(state.get('has_attachments'))

                        # Fetch parameters directly from model's configurations or model's defaults
                        model_configs = app.storage.general.get('model_configurations', {})
                        model_cfg = model_configs.get(model_select.value) or {}
                        
                        model_params = await client.get_model_parameters(model_select.value)
                        
                        temperature = model_cfg.get('temperature') or model_params.get('temperature', 0.7)
                        top_p = model_cfg.get('top_p') or model_params.get('top_p', 0.9)
                        min_p = model_cfg.get('min_p', model_params.get('min_p', 0.0))
                        repeat_penalty = model_cfg.get('repeat_penalty') or model_params.get('repeat_penalty', 1.1)
                        top_k = model_cfg.get('top_k') or model_params.get('top_k', 40)

                        await stream_service.start_generation(
                            stream_id=current_chat_id,
                            messages=messages,
                            model=model_select.value,
                            temperature=temperature,
                            top_p=top_p,
                            min_p=min_p,
                            repeat_penalty=repeat_penalty,
                            top_k=top_k,
                            system_prompt=app.storage.user.get('system_prompt', ''),
                            tool_funcs_map=tool_funcs_map,
                            log_requests=config_manager.is_logging_enabled('chat'),
                            persist_callback=persist_chat,
                            listener=on_stream_event,
                            memory_enabled=memory_enabled,
                            has_attachments=has_attachments
                        )
                    else:
                        ui.notify("Error: No chat ID", type='negative')
                        state['processing'] = False
                        update_button_state()

                async def save_and_respond(msg, new_content):
                    if is_chat_locked():
                        ui.notify("Chat is locked.", type='warning')
                        return
                    if config_manager.is_tts_enabled():
                        asyncio.create_task(asyncio.to_thread(tts_service.warmup))
                    msg['content'] = new_content
                    msg['editing'] = False
                    try:
                        idx = messages.index(msg)
                        del messages[idx+1:]
                    except ValueError: pass
                    app.storage.user['messages'] = list(messages)
                    refresh_chat_ui()
                    asyncio.create_task(save_current_chat())
                    await generate_response()

                chat_renderer.on_save_and_respond = save_and_respond

                async def send_message():
                    if is_chat_locked():
                        ui.notify("Chat is locked.", type='warning')
                        return
                    if state['processing'] or stream_service.any_active() or batch_service.any_active():
                        stream_service.stop_all()
                        batch_service.stop_all()
                        await audio_player.stop()
                        state['stopping'] = True
                        update_button_state()
                        return

                    content = user_input.value.strip()
                    if not content or not model_select.value: return

                    attachments_data = []
                    if attached_files:
                        attachments_data = [{'name': f['name'], 'content': f['content']} for f in attached_files]
                        docs_text = "### Available Documents:\n"
                        for i, f in enumerate(attached_files, 1):
                            docs_text += f"{i}. **Filename:** `{f['name']}` | **ID:** FILE_{i:02d}\n"
                        docs_text += "\n"
                        for i, f in enumerate(attached_files, 1):
                            file_id = f"FILE_{i:02d}"
                            docs_text += f"<{file_id}>\n{f['content']}\n</{file_id}>\n\n"
                        content = f"{docs_text}\n{content}"
                        state['has_attachments'] = True
                        attached_files.clear()
                        refresh_attachments_ui()
                    else:
                        state['has_attachments'] = False
                    
                    user_input.value = ''
                    if config_manager.is_tts_enabled():
                        asyncio.create_task(asyncio.to_thread(tts_service.warmup))
                    
                    user_msg = {
                        'role': 'user', 
                        'content': content, 
                        'id': str(uuid.uuid4()),
                        'attachments': attachments_data
                    }
                    messages.append(user_msg)
                    app.storage.user['messages'] = messages
                    with chat_container: chat_renderer.render_message(user_msg)
                    await scroll_to_bottom()
                    asyncio.create_task(save_current_chat())
                    await generate_response()
                
                user_input.on('keydown.enter.exact', lambda e: send_message() if not e.args['shiftKey'] else None, args=['shiftKey'])

                with ui.row().classes('w-full gap-1 items-center'):
                    ui.button(icon='add', on_click=lambda: uploader.run_method('pickFiles')).props('flat round color=primary').tooltip('Attach text files')
                    ui.button(icon='settings', on_click=open_settings).props('flat round color=grey')

                    tts_btn = ui.button(icon='volume_off').props('flat round color=grey').tooltip('Toggle Automatic Text-to-Speech')
                    def toggle_tts():
                        is_on = not config_manager.is_tts_enabled()
                        config_manager.set_tts_enabled(is_on)
                        tts_btn.props(f"icon={'volume_up' if is_on else 'volume_off'} color={'primary' if is_on else 'grey'}")
                        if is_on: asyncio.create_task(asyncio.to_thread(tts_service.warmup))
                    tts_btn.on('click', toggle_tts)
                    if config_manager.is_tts_enabled(): tts_btn.props("icon=volume_up color=primary")


                    tools_btn = ui.button(icon='construction').props('flat round color=grey').tooltip('Toggle Tools')
                    def toggle_tools():
                        is_on = not app.storage.user.get('tools_enabled', True)
                        app.storage.user['tools_enabled'] = is_on
                        if not is_on:
                            app.storage.user['web_search_enabled'] = False
                            app.storage.user['visual_enabled'] = False
                            app.storage.user['memory_enabled'] = False
                        update_tool_buttons()
                    tools_btn.on('click', toggle_tools)

                    web_search_btn = ui.button(icon='public_off').props('flat round color=grey').tooltip('Toggle Web Search')
                    if not config_manager.is_tool_active('web_search_tool'):
                        web_search_btn.classes('hidden')
                    def toggle_web_search():
                        if not app.storage.user.get('tools_enabled', True):
                            return
                        app.storage.user['web_search_enabled'] = not app.storage.user.get('web_search_enabled', False)
                        update_tool_buttons()
                    web_search_btn.on('click', toggle_web_search)

                    visual_btn = ui.button(icon='brush').props('flat round color=grey').tooltip('Toggle Image Generation')
                    if not config_manager.is_tool_active('visual_tool'):
                        visual_btn.classes('hidden')
                    def toggle_visual():
                        if not app.storage.user.get('tools_enabled', True):
                            return
                        app.storage.user['visual_enabled'] = not app.storage.user.get('visual_enabled', False)
                        update_tool_buttons()
                    visual_btn.on('click', toggle_visual)

                    memory_btn = ui.button(icon='psychology').props('flat round color=grey').tooltip('Toggle User Memory')
                    if not config_manager.is_tool_active('user_memory_tool'):
                        memory_btn.classes('hidden')
                    def toggle_memory():
                        if not app.storage.user.get('tools_enabled', True):
                            return
                        app.storage.user['memory_enabled'] = not app.storage.user.get('memory_enabled', True)
                        update_tool_buttons()
                    memory_btn.on('click', toggle_memory)

                    def update_tool_buttons():
                        tools_on = app.storage.user.get('tools_enabled', True)
                        tools_btn.props(f"icon=construction color={'primary' if tools_on else 'grey'}")

                        web_on = tools_on and app.storage.user.get('web_search_enabled', False)
                        web_search_btn.props(f"icon={'public' if web_on else 'public_off'} color={'primary' if web_on else 'grey'}")

                        visual_on = tools_on and app.storage.user.get('visual_enabled', False)
                        visual_btn.props(f"color={'primary' if visual_on else 'grey'}")

                        memory_on = tools_on and app.storage.user.get('memory_enabled', True)
                        memory_btn.props(f"icon={'psychology' if memory_on else 'psychology_alt'} color={'primary' if memory_on else 'grey'}")

                        if tools_on:
                            if config_manager.is_tool_active('web_search_tool'): web_search_btn.enable()
                            if config_manager.is_tool_active('visual_tool'): visual_btn.enable()
                            if config_manager.is_tool_active('user_memory_tool'): memory_btn.enable()
                        else:
                            web_search_btn.disable()
                            visual_btn.disable()
                            memory_btn.disable()

                    update_tool_buttons()

                    ui.space()
                    send_btn = ui.button(icon='send', on_click=send_message).props('flat round color=primary')
                    
                    def update_encryption_ui():
                        if not current_chat_id:
                            if 'user_input' in locals() and user_input:
                                user_input.props('disable=false')
                                user_input.placeholder = 'Type a message...'
                                if send_btn: send_btn.props('disable=false')
                            return

                        chat = chat_service.load_chat(current_chat_id)
                        if not chat: return
                        
                        if chat.is_encrypted:
                            pw = app.storage.user.get('unlocked_chats', {}).get(current_chat_id)
                            is_unlocked = pw and chat_service.verify_password(current_chat_id, pw)
                            
                            if is_unlocked:
                                if 'user_input' in locals() and user_input:
                                    user_input.props('disable=false')
                                    user_input.placeholder = 'Type a message...'
                                    if send_btn: send_btn.props('disable=false')
                            else:
                                if 'user_input' in locals() and user_input:
                                    user_input.props('disable=true')
                                    user_input.placeholder = 'Chat is locked. Unlock in settings to continue.'
                                    if send_btn: send_btn.props('disable=true')
                        else:
                            if 'user_input' in locals() and user_input:
                                user_input.props('disable=false')
                                user_input.placeholder = 'Type a message...'
                                if send_btn: send_btn.props('disable=false')

                    update_encryption_ui()
                    ui.timer(2.0, update_encryption_ui)
                    
                    if model_select.value: asyncio.create_task(update_params(initial=True))
            
            # Register listener at the end so update_button_state is available
            if current_chat_id:
                stream_service.register_listener(current_chat_id, on_stream_event)
                ui.context.client.on_disconnect(lambda: stream_service.unregister_listener(current_chat_id))
                
                if stream_service.is_streaming(current_chat_id):
                    # If streaming, check if we missed any messages
                    ctx_msgs = stream_service.get_context(current_chat_id)
                    if ctx_msgs:
                        # Sync: if there are messages in ctx that are not in local 'messages', add them
                        # This happens if user navigated away and back
                        local_ids = set(m['id'] for m in messages)
                        for m in ctx_msgs:
                            if m['id'] not in local_ids:
                                messages.append(m) 
                        app.storage.user['messages'] = messages
                        refresh_chat_ui()
                        await scroll_to_bottom()
                        
                    state['processing'] = True
                    update_button_state()
