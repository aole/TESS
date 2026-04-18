from nicegui import ui, app
from utils.ollama_client import client
from utils.config import config_manager
from services.tool_service import tool_service
from services.rating_service import rating_service
from services.chat_service import chat_service
from utils.chat_renderer import ConversationRenderer
from services.stream_service import stream_service
from services.batch_service import batch_service
from services.tts_service import tts_service
import asyncio
import uuid

async def create_page(model_param: str = None, new_chat: bool = False):
    # Use the passed parameter
    query_model = model_param
    # State
    page_client = ui.context.client

    if new_chat:
        # Create a new chat session immediately
        chat = chat_service.create_chat(title="New Chat")
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
    
    state = {'processing': False, 'stopping': False, 'tts_cursors': {}, 'last_update_msg_id': None, 'playing_tts_id': None}

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
    drawer = ui.left_drawer(value=True).classes('bg-[#18181b] border-r border-white/10')
    with drawer:
        with ui.column().classes('w-full h-full p-0 m-0 no-wrap gap-0'):
            # Header
            with ui.row().classes('w-full items-center justify-between p-4 border-b border-white/5 shrink-0'):
                 ui.label('History').classes('text-lg font-bold text-gray-200')
                 ui.button(icon='add', on_click=lambda: load_new_chat()).props('flat round dense color=primary').tooltip('New Chat')
    
            # Chat List
            chat_list_container = ui.column().classes('w-full flex-grow overflow-y-auto p-2 gap-1')

    def load_new_chat():
        nonlocal messages, current_chat_id
        
        if current_chat_id:
            app.storage.user['unlocked_chats'].pop(current_chat_id, None)

        # Create a new chat session immediately so it appears in history
        chat = chat_service.create_chat(title="New Chat")
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
                # Styling for active chat
                is_active = c['id'] == current_chat_id
                bg_class = 'bg-white/10' if is_active else 'hover:bg-white/5'
                
                with ui.card().classes(f'w-full py-1 px-3 text-sm cursor-pointer transition-colors {bg_class} relative group border border-white/5').on('click', lambda _, cid=c['id']: load_chat_by_id(cid)):
                    with ui.column().classes('w-full min-w-0 gap-0'):
                         ui.label(c['title']).classes('font-medium text-gray-200 truncate w-full pr-1')
                         ui.label(c['updated_at'][:10]).classes('text-xs text-gray-500')
                    
                    ui.button(icon='delete').on('click.stop', lambda _, cid=c['id']: delete_chat_history(cid)).props('flat round dense size=sm color=red-4').classes('absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/60')

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
    with ui.dialog() as settings_dialog, ui.card().classes('w-full max-w-lg p-6 bg-[#18181b] border border-white/10'):
        with ui.row().classes('w-full justify-between items-center mb-4'):
             ui.label('Settings').classes('text-xl font-bold text-gray-200')
             ui.button(icon='close', on_click=settings_dialog.close).props('flat round dense color=grey')

        with ui.column().classes('w-full gap-4'):
             # Model Selection

            # Parameters
            with ui.expansion('Parameters', icon='tune').classes('w-full bg-white/5 rounded-lg').props('dense'):
                with ui.column().classes('w-full p-2 gap-2'):
                    temp_slider = ui.slider(min=0, max=1, step=0.1, value=app.storage.user.get('temperature', 0.7)).props('label-always thumb-path=""')
                    ui.label('Temperature').classes('text-xs text-muted')
                    
                    top_p_slider = ui.slider(min=0, max=1, step=0.1, value=app.storage.user.get('top_p', 0.9)).props('label-always')
                    ui.label('Top P').classes('text-xs text-muted')
                    
                    repeat_penalty_slider = ui.slider(min=0, max=2, step=0.1, value=app.storage.user.get('repeat_penalty', 1.1)).props('label-always')
                    ui.label('Repeat Penalty').classes('text-xs text-muted')
                    
                    system_prompt = ui.textarea(label='System Prompt', placeholder='You are a helpful assistant...', value=app.storage.user.get('system_prompt', '')).classes('w-full text-sm').props('rows=3 filled')
                    
             # Sync UI from storage
            def sync_ui_from_storage():
                temp_slider.value = app.storage.user.get('temperature', 0.7)
                top_p_slider.value = app.storage.user.get('top_p', 0.9)
                repeat_penalty_slider.value = app.storage.user.get('repeat_penalty', 1.1)
                system_prompt.value = app.storage.user.get('system_prompt', '')
                
                # Also tool checks
                saved_tools = app.storage.user.get('selected_tools', [])
                for name, box in tool_checks.items():
                    box.value = name in saved_tools

            # Tools
            available_tools = [t for t in tool_service.get_all_tools() if t.active]
            tool_options = {t.name: t for t in available_tools}
            tool_checks = {}
            
            if available_tools:
                with ui.expansion('Tools', icon='construction').classes('w-full bg-white/5 rounded-lg').props('dense'):
                    with ui.column().classes('w-full p-2'):
                         if 'selected_tools' not in app.storage.user:
                             app.storage.user['selected_tools'] = []
                         saved_tools = app.storage.user['selected_tools']

                         def update_tool_storage():
                             selected = [name for name, box in tool_checks.items() if box.value]
                             app.storage.user['selected_tools'] = selected

                         with ui.column().classes('gap-1'):
                             for t_name in tool_options.keys():
                                 is_checked = t_name in saved_tools
                                 tool_checks[t_name] = ui.checkbox(t_name, value=is_checked, on_change=update_tool_storage).classes('text-sm text-gray-300')

            # Tags
            with ui.expansion('Rating Tags', icon='label').classes('w-full bg-white/5 rounded-lg').props('dense'):
                with ui.column().classes('w-full p-2'):
                    current_tags = app.storage.user.get('tags', ["General", "Coding", "Tools", "Writing"])
                    
                    def update_tags(e):
                        tags = [t.strip() for t in e.value.split(',') if t.strip()]
                        if not tags: tags = ["General"]
                        app.storage.user['tags'] = tags
                        # Update renderer if it exists
                        try:
                           chat_renderer.available_tags = tags
                        except:
                           pass

                    ui.input('Tags (comma separated)', value=", ".join(current_tags), on_change=update_tags).classes('w-full').props('dense debounce=500')

            # Security (Encryption)
            with ui.expansion('Security', icon='security').classes('w-full bg-white/5 rounded-lg').props('dense'):
                with ui.column().classes('w-full p-2 gap-2'):
                    ui.label('Protect your chat history with a password.').classes('text-xs text-gray-400')
                    settings_encrypt_btn = ui.button('Encrypt Chat', icon='lock').props('outline color=primary').classes('w-full')
                    settings_remove_enc_btn = ui.button('Remove Encryption', icon='lock_open').props('outline color=negative').classes('w-full hidden')
                    settings_unlock_btn = ui.button('Unlock Chat', icon='key').props('outline color=warning').classes('w-full hidden')
                    settings_lock_btn = ui.button('Lock Chat', icon='lock').props('outline color=warning').classes('w-full hidden')

            # Ratings
            ratings_section = ui.expansion('Model Ratings', icon='star').classes('w-full bg-white/5 rounded-lg hidden').props('dense')
            stats_content = ui.column().classes('w-full p-2 gap-1')
            with ratings_section:
                stats_content.move(ratings_section) # Ensure content is inside

            async def update_ratings_display(model):
                 stats = rating_service.get_model_stats(model)
                 if stats:
                     ratings_section.classes(remove='hidden')
                     stats_content.clear()
                     with stats_content:
                         for tag, data in stats.items():
                             with ui.row().classes('w-full justify-between items-center text-xs'):
                                 ui.label(tag).classes('text-gray-300')
                                 ui.label(f"{data['average']}★ ({data['count']})").classes('text-yellow-400')
                 else:
                     ratings_section.classes(add='hidden')

            def clear_chat():
                messages.clear()
                app.storage.user['messages'] = []
                if 'refresh_chat_ui' in locals():
                    refresh_chat_ui()
                settings_dialog.close()

            async def save_settings():
                app.storage.user['temperature'] = temp_slider.value
                app.storage.user['top_p'] = top_p_slider.value
                app.storage.user['repeat_penalty'] = repeat_penalty_slider.value
                app.storage.user['system_prompt'] = system_prompt.value
                ui.notify('Settings saved and persisted', type='positive')
                settings_dialog.close()

            async def restore_defaults():
                if not model_select.value:
                    ui.notify("No model selected", type='warning')
                    return
                
                try:
                    params = await client.get_model_parameters(model_select.value)
                    
                    # Default fallbacks if not specified in model
                    # Using app defaults: Temp=0.7, TopP=0.9, RepPen=1.1
                    temp_slider.value = params.get('temperature', 0.7)
                    top_p_slider.value = params.get('top_p', 0.9)
                    repeat_penalty_slider.value = params.get('repeat_penalty', 1.1)
                    
                    # System prompt
                    system_prompt.value = params.get('system', '')
                        
                    ui.notify(f"Restored defaults for {model_select.value}", type='info')
                        
                except Exception as e:
                    ui.notify(f"Error restoring defaults: {e}", type='negative')

            ui.button('Save Changes', on_click=save_settings).props('flat color=primary').classes('w-full mt-4')
            with ui.row().classes('w-full gap-2 items-center'):
                ui.button('Clear Chat', on_click=clear_chat).props('outline color=negative').classes('flex-grow')
                ui.button('Defaults', on_click=restore_defaults).props('outline color=grey').classes('flex-grow')

            # Parameter update logic
            async def update_params(initial=False):
                if not model_select.value: return
                
                # Update ratings and storage
                await update_ratings_display(model_select.value)
                app.storage.user['selected_model'] = model_select.value

                with model_select:
                    # Update URL without reload
                    from urllib.parse import quote
                    safe_model = quote(model_select.value)
                    await ui.run_javascript(f"window.history.replaceState(null, '', '/chat?model={safe_model}');")

                    # If this is the initial load and we have saved settings, don't overwrite them with model defaults
                    has_saved = any(k in app.storage.user for k in ['temperature', 'top_p', 'repeat_penalty', 'system_prompt'])
                    if initial and has_saved:
                        return

                    new_params = await client.get_model_parameters(model_select.value)
                    
                    # Check for differences
                    diffs = []
                    if 'temperature' in new_params and abs(new_params['temperature'] - temp_slider.value) > 0.01:
                        diffs.append(f"Temperature: {temp_slider.value} → {new_params['temperature']}")
                    if 'top_p' in new_params and abs(new_params['top_p'] - top_p_slider.value) > 0.01:
                        diffs.append(f"Top P: {top_p_slider.value} → {new_params['top_p']}")
                    if 'repeat_penalty' in new_params and abs(new_params['repeat_penalty'] - repeat_penalty_slider.value) > 0.01:
                        diffs.append(f"Repeat Penalty: {repeat_penalty_slider.value} → {new_params['repeat_penalty']}")
                    
                    new_sys = new_params.get('system', '')
                    if new_sys != system_prompt.value:
                        diffs.append("System Prompt will change")

                    if not initial and diffs:
                        with ui.dialog() as confirm_dialog, ui.card().classes('p-6 bg-[#18181b] border border-white/10'):
                            ui.label('Apply Model Defaults?').classes('text-xl font-bold text-gray-200 mb-2')
                            ui.label('The new model has different default parameters:').classes('text-sm text-gray-400 mb-4')
                            for d in diffs:
                                ui.label(f"• {d}").classes('text-xs text-gray-500 ml-2')
                            
                            with ui.row().classes('w-full justify-end gap-2 mt-6'):
                                ui.button('Keep Current', on_click=lambda: confirm_dialog.submit(False)).props('flat color=grey')
                                ui.button('Apply New', on_click=lambda: confirm_dialog.submit(True)).props('flat color=primary')
                        
                        should_update = await confirm_dialog
                        if not should_update:
                            return

                    # Apply updates
                    if 'temperature' in new_params:
                        temp_slider.value = new_params['temperature']
                    if 'top_p' in new_params:
                        top_p_slider.value = new_params['top_p']
                    if 'repeat_penalty' in new_params:
                        repeat_penalty_slider.value = new_params['repeat_penalty']
                    if 'system' in new_params:
                        system_prompt.value = new_params['system']


    # Layout (just chat area now)
    with ui.row().classes('w-full max-w-[1200px] mx-auto h-[calc(100vh-3rem)] pt-14 px-4 items-stretch flex-nowrap'):
        # --- Right Area (Chat) ---
        with ui.column().classes('flex-grow h-full gap-2 relative min-w-0'):
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
                if msg in messages:
                    messages.remove(msg)
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
                await update_ratings_display(msg.get('model', 'unknown'))
                chat_renderer.render_messages(messages)

            async def handle_delete_rating(msg, tag):
                if not msg.get('id'): return
                rating_service.remove_rating(msg['id'], tag)
                ui.notify(f"Removed rating for {tag}", type='info')
                await update_ratings_display(msg.get('model', 'unknown'))
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
                on_play_tts=lambda msg: asyncio.create_task(handle_play_tts(msg)),
                get_playing_tts_id=lambda: state.get('playing_tts_id'),
                get_ratings=get_msg_ratings,
                available_tags=app.storage.user.get('tags', ["General", "Coding", "Tools", "Writing"]),
                on_save_and_respond=None # Will be set later
            )
            async def play_audio_js(b64_str):
                await ui.run_javascript(f"""
                    if (!window.audioQueue) {{
                        window.audioQueue = [];
                        window.isPlayingAudio = false;
                        window.currentAudioObj = null;
                        
                        window.stopAudio = function() {{
                            window.audioQueue = [];
                            if (window.currentAudioObj) {{
                                window.currentAudioObj.pause();
                                window.currentAudioObj = null;
                            }}
                            window.isPlayingAudio = false;
                        }};
                        
                        window.playNextAudio = function() {{
                            if (window.audioQueue.length > 0 && !window.isPlayingAudio) {{
                                window.isPlayingAudio = true;
                                let src = window.audioQueue.shift();
                                window.currentAudioObj = new Audio('data:audio/wav;base64,' + src);
                                window.currentAudioObj.onended = function() {{
                                    window.isPlayingAudio = false;
                                    window.playNextAudio();
                                }};
                                window.currentAudioObj.play().catch(e => {{
                                    console.error("Audio play error", e);
                                    window.isPlayingAudio = false;
                                    window.playNextAudio();
                                }});
                            }}
                        }};
                    }}
                    window.audioQueue.push('{b64_str}');
                    window.playNextAudio();
                """)
                
            async def stop_playback():
                with page_client:
                    await ui.run_javascript("if(window.stopAudio) window.stopAudio();")
                state['playing_tts_id'] = None
                
            async def handle_play_tts(msg):
                if state.get('playing_tts_id') == msg['id']:
                    await stop_playback()
                    with page_client:
                        chat_renderer.render_messages(messages)
                    return
                    
                await stop_playback()
                state['playing_tts_id'] = msg['id']
                with page_client:
                    chat_renderer.render_messages(messages)
                
                content = msg.get('content', '')
                import re
                boundary_pattern = (
                    r'(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bProf)'
                    r'(?<!\bSr)(?<!\bJr)(?<!\bSt)(?<!\bCapt)(?<!\bCol)'
                    r'(?<!\bGen)(?<!\bLt)(?<!\bSgt)(?<!\b[A-Za-z])'
                    r'([.!?\n]+)(\s*)'
                )
                
                # Split and keep delimiters
                parts = re.split(boundary_pattern, content, flags=re.IGNORECASE)
                sentences = []
                current_s = ""
                for i in range(0, len(parts), 3):
                    current_s += parts[i]
                    if i + 1 < len(parts): current_s += parts[i+1] # delim
                    if i + 2 < len(parts): current_s += parts[i+2] # space
                    
                    if current_s.strip():
                        sentences.append(current_s)
                        current_s = ""
                if current_s.strip():
                    sentences.append(current_s)
                    
                for s in sentences:
                    if state.get('playing_tts_id') != msg['id']:
                        break
                    await play_tts(s)

            tts_lock = asyncio.Lock()
            async def play_tts(text_chunk):
                async with tts_lock:
                    try:
                        b64_list = await asyncio.to_thread(tts_service.generate_audio_b64, text_chunk)
                        for b64 in b64_list:
                            with page_client:
                                await play_audio_js(b64)
                    except Exception as e:
                        print(f"TTS Error: {e}")
            
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
                        if app.storage.user.get('tts_enabled', False):
                            if msg_id not in state['tts_cursors']:
                                state['tts_cursors'][msg_id] = 0
                            
                            spoken = state['tts_cursors'][msg_id]
                            unspoken = content[spoken:]
                            import re
                            
                            # Prevent splitting on common abbreviations and single-letter initials
                            boundary_pattern = (
                                r'(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bProf)'
                                r'(?<!\bSr)(?<!\bJr)(?<!\bSt)(?<!\bCapt)(?<!\bCol)'
                                r'(?<!\bGen)(?<!\bLt)(?<!\bSgt)(?<!\b[A-Za-z])'
                                r'([.!?\n]+)(\s+)'
                            )
                            
                            matches = list(re.finditer(boundary_pattern, unspoken, re.IGNORECASE))
                            
                            flush_end_pos = None
                            if matches:
                                flush_end_pos = matches[0].end()
                                    
                            if flush_end_pos is not None:
                                sentence = unspoken[:flush_end_pos]
                                state['tts_cursors'][msg_id] += flush_end_pos
                                asyncio.create_task(play_tts(sentence))
                                
                    elif event_type == 'done':
                        state['processing'] = False
                        state['stopping'] = False
                        update_button_state()
                        
                        # handle trailing text for TTS
                        last_id = state.get('last_update_msg_id')
                        if last_id and app.storage.user.get('tts_enabled', False):
                            spoken = state['tts_cursors'].get(last_id, 0)
                            for m in messages:
                                if m.get('id') == last_id:
                                    final_unspoken = m.get('content', '')[spoken:]
                                    if final_unspoken.strip():
                                        state['tts_cursors'][last_id] += len(final_unspoken)
                                        asyncio.create_task(play_tts(final_unspoken))
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
            
            async def prompt_encryption():
                with ui.dialog() as d, ui.card().classes('bg-[#18181b] border border-white/10'):
                    ui.label('Encrypt Chat').classes('text-lg font-bold text-gray-200')
                    pw1 = ui.input('Password', password=True, password_toggle_button=True).classes('w-full')
                    pw2 = ui.input('Confirm Password', password=True, password_toggle_button=True).classes('w-full')
                    
                    async def do_encrypt():
                        nonlocal messages
                        if not pw1.value or pw1.value != pw2.value:
                            ui.notify('Passwords do not match or empty', type='negative')
                            return
                        chat = chat_service.load_chat(current_chat_id)
                        if chat:
                            import secrets
                            chat.is_encrypted = True
                            chat.salt = secrets.token_hex(16)
                            
                            garbage_messages = chat_service.encrypt_messages(messages, pw1.value, chat.salt)
                            chat.messages = garbage_messages
                            chat_service.save_chat(chat, update_timestamp=False)
                            
                            # Do NOT add to unlocked_chats, so it immediately locks and renders garbage
                            app.storage.user['unlocked_chats'].pop(current_chat_id, None)
                            
                            # Replace local messages and re-render
                            messages.clear()
                            messages.extend(garbage_messages)
                            app.storage.user['messages'] = messages
                            refresh_chat_ui()
                            
                            ui.notify('Chat encrypted', type='positive')
                            update_encryption_ui()
                        d.close()
                    ui.button('Encrypt', on_click=do_encrypt).props('color=primary').classes('w-full mt-2')
                await d

            async def prompt_unlock():
                with ui.dialog() as d, ui.card().classes('bg-[#18181b] border border-white/10'):
                    ui.label('Unlock Chat').classes('text-lg font-bold text-gray-200')
                    pw = ui.input('Password', password=True, password_toggle_button=True).classes('w-full').on('keydown.enter', lambda: do_unlock())
                    
                    async def do_unlock():
                        if chat_service.verify_password(current_chat_id, pw.value):
                            app.storage.user['unlocked_chats'][current_chat_id] = pw.value
                            load_chat_by_id(current_chat_id)
                            ui.notify('Chat unlocked', type='positive')
                            d.close()
                        else:
                            ui.notify('Incorrect password', type='negative')
                    ui.button('Unlock', on_click=do_unlock).props('color=warning').classes('w-full mt-2')
                await d

            async def prompt_remove_encryption():
                chat = chat_service.load_chat(current_chat_id)
                if chat:
                    chat.is_encrypted = False
                    chat.salt = None
                    app.storage.user['unlocked_chats'].pop(current_chat_id, None)
                    chat.messages = messages
                    chat_service.save_chat(chat, update_timestamp=False)
                    ui.notify('Encryption removed', type='info')
                    update_encryption_ui()

            def do_lock():
                app.storage.user['unlocked_chats'].pop(current_chat_id, None)
                load_chat_by_id(current_chat_id)
                ui.notify('Chat locked', type='info')

            settings_encrypt_btn.on('click', prompt_encryption)
            settings_remove_enc_btn.on('click', prompt_remove_encryption)
            settings_unlock_btn.on('click', prompt_unlock)
            settings_lock_btn.on('click', do_lock)

            # Input Area
            with ui.row().classes('w-full items-end gap-2 p-2 glass-panel rounded-lg'):
                user_input = ui.textarea(placeholder='Type a message...').classes('w-full flex-grow').props('autogrow bg-color=transparent borderless dense rows=1')
                
                # Forward declaration for button
                send_btn = None

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
                
                # Poll for global updates
                ui.timer(1.0, update_button_state)

                def update_encryption_ui():
                    if not current_chat_id:
                        settings_encrypt_btn.classes(add='hidden')
                        settings_unlock_btn.classes(add='hidden')
                        settings_lock_btn.classes(add='hidden')
                        settings_remove_enc_btn.classes(add='hidden')
                        if 'user_input' in locals() and user_input:
                            user_input.props('disable=false')
                            user_input.placeholder = 'Type a message...'
                            if send_btn: send_btn.props('disable=false')
                        return

                    chat = chat_service.load_chat(current_chat_id)
                    if not chat: return
                    
                    if chat.is_encrypted:
                        settings_encrypt_btn.classes(add='hidden')
                        pw = app.storage.user['unlocked_chats'].get(current_chat_id)
                        is_unlocked = pw and chat_service.verify_password(current_chat_id, pw)
                        
                        if is_unlocked:
                            settings_unlock_btn.classes(add='hidden')
                            settings_lock_btn.classes(remove='hidden')
                            settings_remove_enc_btn.classes(remove='hidden')
                            if 'user_input' in locals() and user_input:
                                user_input.props('disable=false')
                                user_input.placeholder = 'Type a message...'
                                if send_btn: send_btn.props('disable=false')
                        else:
                            settings_unlock_btn.classes(remove='hidden')
                            settings_lock_btn.classes(add='hidden')
                            settings_remove_enc_btn.classes(add='hidden')
                            if 'user_input' in locals() and user_input:
                                user_input.props('disable=true')
                                user_input.placeholder = 'Chat is locked. Unlock to continue or view.'
                                if send_btn: send_btn.props('disable=true')
                    else:
                        settings_encrypt_btn.classes(remove='hidden')
                        settings_unlock_btn.classes(add='hidden')
                        settings_lock_btn.classes(add='hidden')
                        settings_remove_enc_btn.classes(add='hidden')
                        if 'user_input' in locals() and user_input:
                            user_input.props('disable=false')
                            user_input.placeholder = 'Type a message...'
                            if send_btn: send_btn.props('disable=false')

                update_encryption_ui()
                # Run periodically just in case
                ui.timer(2.0, update_encryption_ui)

                # --- Core Generation Logic ---
                async def generate_response():
                    if state['processing'] and not state['stopping']:
                         return

                    state['processing'] = True
                    state['stopping'] = False
                    update_button_state()

                    # Prepare functions map
                    tool_funcs_map = {}
                    if available_tools:
                        for name, checkbox in tool_checks.items():
                            if checkbox.value and name in tool_options:
                                func = load_tool_function(name, tool_options[name].code)
                                if func:
                                    tool_funcs_map[func.__name__] = func
                    
                    if not current_chat_id:
                         # Should have been created by send_message or save_current_chat
                         await save_current_chat()
                    
                    if current_chat_id:
                        # Register listener if not already (safeguard)
                        stream_service.register_listener(current_chat_id, on_stream_event)
                        
                        # Define persistence callback
                        async def persist_chat(updated_messages):
                            # The messages list is updated in place, but we need to ensure the chat object is saved
                            if current_chat_id:
                                chat = chat_service.load_chat(current_chat_id)
                                if chat:
                                    chat.messages = updated_messages
                                    chat_service.save_chat(chat)

                        await stream_service.start_generation(
                            stream_id=current_chat_id,
                            messages=messages,
                            model=model_select.value,
                            temperature=temp_slider.value,
                            top_p=top_p_slider.value,
                            repeat_penalty=repeat_penalty_slider.value,
                            system_prompt=system_prompt.value,
                            tool_funcs_map=tool_funcs_map,
                            log_requests=config_manager.is_logging_enabled('chat'),
                            persist_callback=persist_chat,
                            listener=on_stream_event
                        )
                    else:
                        ui.notify("Error: No chat ID", type='negative')
                        state['processing'] = False
                        update_button_state()

                # --- User Action Handlers ---
                async def save_and_respond(msg, new_content):
                    if app.storage.user.get('tts_enabled', False):
                        asyncio.create_task(asyncio.to_thread(tts_service.warmup))
                    msg['content'] = new_content
                    msg['editing'] = False
                    
                    try:
                        idx = messages.index(msg)
                        del messages[idx+1:]
                    except ValueError:
                        pass
                    
                    app.storage.user['messages'] = list(messages)
                    refresh_chat_ui()
                    asyncio.create_task(save_current_chat())
                    await generate_response()

                chat_renderer.on_save_and_respond = save_and_respond

                async def send_message():
                    # Global Stop Check
                    if state['processing'] or stream_service.any_active() or batch_service.any_active():
                        stream_service.stop_all()
                        batch_service.stop_all()
                        state['stopping'] = True
                        update_button_state()
                        return

                    content = user_input.value.strip()
                    if not content or not model_select.value: return
                    
                    user_input.value = ''
                    
                    if app.storage.user.get('tts_enabled', False):
                        asyncio.create_task(asyncio.to_thread(tts_service.warmup))
                    
                    user_msg = {'role': 'user', 'content': content, 'id': str(uuid.uuid4())}
                    messages.append(user_msg)
                    app.storage.user['messages'] = messages
                    
                    with chat_container:
                        chat_renderer.render_message(user_msg)
                        
                    await scroll_to_bottom()
                    asyncio.create_task(save_current_chat())
                    
                    await generate_response()
                
                user_input.on('keydown.enter.exact',
                    lambda e: send_message() if not e.args['shiftKey'] else None, 
                    args=['shiftKey']
                )

                def open_settings():
                    sync_ui_from_storage()
                    settings_dialog.open()

                with ui.row().classes('gap-1 items-center'):
                    send_btn = ui.button(icon='send', on_click=send_message).props('flat round color=primary')
                    ui.button(icon='settings', on_click=open_settings).props('flat round color=grey')

                    model_select = ui.select(
                        options=model_options,
                        value=default_model,
                    ).props('dense options-dense borderless').classes('w-48 text-sm text-gray-400')
                    
                    tts_btn = ui.button(icon='volume_off').props('flat round color=grey').tooltip('Toggle Text-to-Speech')
                    def toggle_tts():
                        app.storage.user['tts_enabled'] = not app.storage.user.get('tts_enabled', False)
                        is_on = app.storage.user['tts_enabled']
                        tts_btn.props(f"icon={'volume_up' if is_on else 'volume_off'} color={'primary' if is_on else 'grey'}")
                        if is_on:
                            # Preload pipeline and warm up on first click
                            asyncio.create_task(asyncio.to_thread(tts_service.warmup))
                    tts_btn.on('click', toggle_tts)
                    if app.storage.user.get('tts_enabled', False):
                        tts_btn.props("icon=volume_up color=primary")
                        
                    model_select.on_value_change(lambda e: update_params())
                    # Trigger initial update
                    if model_select.value:
                        asyncio.create_task(update_params(initial=True))
            
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
