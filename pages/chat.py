from nicegui import ui, app
from utils.ollama_client import client
from utils.config import config_manager
from services.tool_service import tool_service
from services.rating_service import rating_service
from services.chat_service import chat_service
from utils.chat_renderer import ConversationRenderer
import asyncio
import uuid

async def create_page(model_param: str = None):
    # Use the passed parameter
    query_model = model_param
    # State
    if 'messages' not in app.storage.user:
        app.storage.user['messages'] = []
    if 'chat_id' not in app.storage.user:
        app.storage.user['chat_id'] = None

    # We use lists/dicts in storage, distinct from the local variables
    # We reference them here, but we must be careful to update the storage when we change them.
    # To simplify, we will update app.storage.user['messages'] explicitly.
    
    messages = app.storage.user['messages']
    current_chat_id = app.storage.user['chat_id'] 

    # Ensure all messages have IDs
    for msg in messages:
        if 'id' not in msg:
            msg['id'] = str(uuid.uuid4())
    
    state = {'processing': False, 'stopping': False}

    # Model Selection Logic (Prep)
    try:
        models_data = await client.list_models()
        model_options = [m['model'] for m in models_data]
    except Exception as e:
        model_options = []
        ui.notify(f"Error loading models: {e}", type='negative')

    # Use query param model if available and valid
    default_model = model_options[0] if model_options else None
    if query_model and query_model in model_options:
        default_model = query_model

    # --- Persistance Helper ---
    async def save_current_chat():
        nonlocal current_chat_id
        if not messages: 
            return # Don't save empty chats unless they already exist? 
                   # Actually, if we just created a "New Chat" and haven't typed, we might not want to save it yet.
        
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
                    chat.messages = messages
                    chat.title = title # Update title dynamically? Maybe only if it was "New Chat"? 
                                      # For now, let's update it if it's the first message or so. 
                                      # Simple approach: always update title based on first message if chat is short?
                                      # Let's just update messages for now.
                    # Actually, if title is "New Chat", update it.
                    if chat.title == "New Chat" and title != "New Chat":
                        chat.title = title
                    
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
    drawer = ui.left_drawer(value=True).classes('bg-[#18181b] border-r border-white/10 flex flex-col')
    with drawer:
        # Header
        with ui.row().classes('w-full items-center justify-between p-4 border-b border-white/5'):
             ui.label('History').classes('text-lg font-bold text-gray-200')
             ui.button(icon='add', on_click=lambda: load_new_chat()).props('flat round dense color=primary').tooltip('New Chat')

        # Chat List
        chat_list_container = ui.column().classes('w-full flex-grow overflow-y-auto p-2 gap-1')

    def load_new_chat():
        nonlocal messages, current_chat_id
        # Save current if needed? (It should happen on message send)
        
        messages = []
        current_chat_id = None
        app.storage.user['messages'] = messages
        app.storage.user['chat_id'] = None
        
        if 'refresh_chat_ui' in locals():
            refresh_chat_ui()
        refresh_chat_list()
        # Optionally close drawer on mobile?
    
    def load_chat_by_id(chat_id):
        nonlocal messages, current_chat_id
        chat = chat_service.load_chat(chat_id)
        if chat:
            messages = chat.messages
            current_chat_id = chat.id
            app.storage.user['messages'] = messages
            app.storage.user['chat_id'] = current_chat_id
            if 'refresh_chat_ui' in locals():
                refresh_chat_ui()
            refresh_chat_list()
        else:
            ui.notify("Could not load chat", type='negative')

    def delete_chat_history(chat_id):
        chat_service.delete_chat(chat_id)
        refresh_chat_list()
        if current_chat_id == chat_id:
            load_new_chat()

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
                
                with ui.card().classes(f'w-full p-3 text-sm cursor-pointer transition-colors {bg_class} relative group border border-white/5').on('click', lambda _, cid=c['id']: load_chat_by_id(cid)):
                    with ui.row().classes('w-full justify-between items-center gap-2'):
                         with ui.column().classes('flex-grow min-w-0 gap-0'):
                             ui.label(c['title']).classes('font-medium text-gray-200 truncate w-full')
                             ui.label(c['updated_at'][:10]).classes('text-xs text-gray-500')
                         
                         ui.button(icon='delete').on('click.stop', lambda _, cid=c['id']: delete_chat_history(cid)).props('flat round dense size=xs color=grey').classes('opacity-0 group-hover:opacity-100 transition-opacity')

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

            ui.button('Save Changes', on_click=save_settings).props('flat color=primary').classes('w-full mt-4')
            ui.button('Clear Chat', on_click=clear_chat).props('outline color=negative').classes('w-full mt-2')

            # Parameter update logic
            async def update_params(initial=False):
                if not model_select.value: return
                
                # Update ratings
                await update_ratings_display(model_select.value)

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
                get_ratings=get_msg_ratings
            )
            
            def refresh_chat_ui():
                chat_renderer.render_messages(messages)

            # Scroll init
            if messages:
                refresh_chat_ui()
                await scroll_to_bottom()

            # Input Area
            with ui.row().classes('w-full items-end gap-2 p-2 glass-panel rounded-lg'):
                user_input = ui.textarea(placeholder='Type a message...').classes('w-full flex-grow').props('autogrow bg-color=transparent borderless dense rows=1')
                
                # Forward declaration for button
                send_btn = None

                def update_button_state():
                    if not send_btn: return
                    if state['processing']:
                        if state['stopping']:
                            send_btn.props('icon=hourglass_empty color=warning')
                        else:
                            send_btn.props('icon=stop color=negative')
                    else:
                        send_btn.props('icon=send color=primary')

                # --- Core Generation Logic ---
                async def generate_response():
                    if state['processing']:
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
                    
                    # Helper to execute tool
                    async def execute_tool_call(tool_call):
                        try:
                            fname = tool_call.get('function', {}).get('name')
                            args = tool_call.get('function', {}).get('arguments', {})
                            if fname in tool_funcs_map:
                                func = tool_funcs_map[fname]
                                import inspect
                                if asyncio.iscoroutinefunction(func):
                                    res = await func(**args)
                                else:
                                    res = func(**args)
                                return str(res)
                            else:
                                return f"Error: Tool {fname} not found"
                        except Exception as e:
                            return f"Error executing tool: {e}"
                    
                    # Prepare initial messages
                    api_messages = []
                    sys_content = system_prompt.value or ""
                    if tool_funcs_map: # If tools are active
                        sys_content += "\n\nIMPORTANT: When generating tool calls, ensure strictly valid JSON. Do not use invalid escape sequences like '\\?' inside strings. Only escape backslashes and double quotes."
                        if not system_prompt.value: # If user didn't provide one, start with a generic helpful one
                            sys_content = "You are a helpful assistant.\n" + sys_content
                    
                    if sys_content:
                        api_messages.append({'role': 'system', 'content': sys_content})
                    
                    for msg in messages:
                        if msg['role'] in ['user', 'assistant', 'tool']:
                            clean_msg = {k:v for k,v in msg.items() if k in ['role', 'content', 'images', 'tool_calls']}
                            api_messages.append(clean_msg)
                    
                    # Conversation Loop
                    while True:
                        response_content = ""
                        full_thinking = ""
                        tool_calls = []
                        
                        # Create Placeholder Message
                        msg_id = str(uuid.uuid4())
                        assistant_msg = {
                            'role': 'assistant', 
                            'content': '', 
                            'thinking': '', 
                            'model': model_select.value,
                            'id': msg_id
                        }
                        
                        messages.append(assistant_msg)
                        
                        # Render new message to UI
                        with chat_container:
                            chat_renderer.render_message(assistant_msg)
                            
                        await scroll_to_bottom()
                        
                        try:
                            list_tools = list(tool_funcs_map.values()) if tool_funcs_map else None
                            stream = await client.chat(
                                model=model_select.value,
                                messages=api_messages,
                                stream=True,
                                options={
                                    'temperature': temp_slider.value,
                                    'top_p': top_p_slider.value,
                                    'repeat_penalty': repeat_penalty_slider.value
                                },
                                tools=list_tools,
                                log_requests=config_manager.is_logging_enabled('chat')
                            )
                            
                            async for chunk in stream:
                                if state['stopping']:
                                    if not response_content and not full_thinking:
                                        response_content = '_Stopped by user_'
                                        assistant_msg['content'] = response_content
                                        await chat_renderer.update_message(msg_id, response_content, full_thinking, tool_calls)
                                    break

                                msg_chunk = chunk.get('message', {})
                                part = msg_chunk.get('content') or ''
                                thinking_part = msg_chunk.get('thinking', '')
                                tool_calls_part = msg_chunk.get('tool_calls', [])
                                
                                if thinking_part:
                                    full_thinking += thinking_part
                                
                                if tool_calls_part:
                                    tool_calls.extend(tool_calls_part)
                                
                                if part:
                                    response_content += part
                                    
                                # Streaming Update
                                await chat_renderer.update_message(msg_id, response_content, full_thinking, tool_calls)
                                await scroll_to_bottom(check_position=True)
                                
                            # Finalize Message Data
                            assistant_msg['content'] = response_content
                            assistant_msg['thinking'] = full_thinking
                            if tool_calls:
                                assistant_msg['tool_calls'] = tool_calls
                            
                            # Clean for API
                            clean_assist = {k:v for k,v in assistant_msg.items() if k in ['role', 'content', 'tool_calls']}
                            api_messages.append(clean_assist) 

                            # Persist
                            app.storage.user['messages'] = messages
                            asyncio.create_task(save_current_chat())
                            
                            if state['stopping']:
                                break

                            # Handle Tools
                            if tool_calls:
                                for tc in tool_calls:
                                    res = await execute_tool_call(tc)
                                    tool_msg = {
                                        'role': 'tool',
                                        'content': res,
                                        'name': tc.get('function', {}).get('name'),
                                        'id': str(uuid.uuid4())
                                    }
                                    messages.append(tool_msg)
                                    api_messages.append({'role': 'tool', 'content': res}) 
                                    
                                    with chat_container:
                                        chat_renderer.render_message(tool_msg)
                                    await scroll_to_bottom(check_position=True)
                                
                                asyncio.create_task(save_current_chat())
                            else:
                                break # Turn ends

                        except Exception as e:
                            ui.notify(f'Error: {e}', type='negative')
                            break
                    
                    state['processing'] = False
                    state['stopping'] = False
                    update_button_state()
                    refresh_chat_ui() # Ensure clean state

                # --- User Action Handlers ---
                async def save_and_respond(msg, new_content):
                    msg['content'] = new_content
                    msg['editing'] = False
                    
                    try:
                        idx = messages.index(msg)
                        del messages[idx+1:]
                    except ValueError:
                        pass
                    
                    app.storage.user['messages'] = messages
                    refresh_chat_ui()
                    asyncio.create_task(save_current_chat())
                    asyncio.create_task(generate_response())

                async def send_message():
                    if state['processing']:
                        state['stopping'] = True
                        update_button_state()
                        return

                    content = user_input.value.strip()
                    if not content or not model_select.value: return
                    
                    user_input.value = ''
                    
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

                with ui.row().classes('gap-1 items-center'):
                    send_btn = ui.button(icon='send', on_click=send_message).props('flat round color=primary')
                    ui.button(icon='settings', on_click=settings_dialog.open).props('flat round color=grey')

                    model_select = ui.select(
                        options=model_options,
                        value=default_model,
                    ).props('dense options-dense borderless').classes('w-48 text-sm text-gray-400')
                    
                    model_select.on_value_change(lambda e: update_params())
                    # Trigger initial update
                    if model_select.value:
                        asyncio.create_task(update_params(initial=True))
