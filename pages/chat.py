from nicegui import ui, app
from utils.ollama_client import client
from utils.config import config_manager
from services.tool_service import tool_service
from services.rating_service import rating_service
import asyncio
import uuid

async def create_page(model_param: str = None):
    # Use the passed parameter
    query_model = model_param
    # State
    if 'messages' not in app.storage.user:
        app.storage.user['messages'] = []
    messages = app.storage.user['messages']

    # Ensure all messages have IDs
    for msg in messages:
        if 'id' not in msg:
            msg['id'] = str(uuid.uuid4())
    
    state = {'processing': False, 'stopping': False}

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
    
    # Layout using a row for sidebar + chat
    with ui.row().classes('w-full max-w-[1200px] mx-auto h-[calc(100vh-3rem)] pt-14 px-4 gap-6 items-stretch flex-nowrap'):
        
        # --- Left Sidebar (Controls) ---
        with ui.column().classes('w-72 shrink-0 gap-4'):
             # Model Ratings Stats
            ratings_container = ui.card().classes('w-full p-3 gap-2 bg-black/20 border-white/5 hidden')
            with ratings_container:
                ui.label('Model Ratings').classes('text-sm font-bold text-gray-400 mb-1')
                stats_content = ui.column().classes('w-full gap-1')

            async def update_ratings_sidebar(model):
                 stats = rating_service.get_model_stats(model)
                 if stats:
                     ratings_container.classes(remove='hidden')
                     stats_content.clear()
                     with stats_content:
                         for tag, data in stats.items():
                             with ui.row().classes('w-full justify-between items-center text-xs'):
                                 ui.label(tag).classes('text-gray-300')
                                 ui.label(f"{data['average']}★ ({data['count']})").classes('text-yellow-400')
                 else:
                     ratings_container.classes(add='hidden')

            # Model Selection
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
            
            with ui.card().classes('w-full p-3 gap-2 bg-black/20 border-white/5'):
                ui.label('Model Settings').classes('text-sm font-bold text-gray-400 mb-1')
                model_select = ui.select(
                    options=model_options,
                    label='Model',
                    value=default_model,
                ).props('dense options-dense').classes('w-full')

                ui.separator().classes('bg-white/10 my-1')
                
                # Parameters
                temp_slider = ui.slider(min=0, max=1, step=0.1, value=0.7).props('label-always thumb-path=""')
                ui.label('Temperature').classes('text-xs text-muted mb-2')
                
                top_p_slider = ui.slider(min=0, max=1, step=0.1, value=0.9).props('label-always')
                ui.label('Top P').classes('text-xs text-muted mb-2')
                
                repeat_penalty_slider = ui.slider(min=0, max=2, step=0.1, value=1.1).props('label-always')
                ui.label('Repeat Penalty').classes('text-xs text-muted mb-2')
                
                system_prompt = ui.textarea(label='System Prompt', placeholder='You are a helpful assistant...').classes('w-full text-sm').props('rows=5')
                
                def clear_chat():
                    messages.clear()
                    app.storage.user['messages'] = []
                    render_chat_messages.refresh()
                
                ui.button('Clear Chat', on_click=clear_chat).props('outline color=negative').classes('w-full mt-2')

            # --- Tools Selection ---
            available_tools = [t for t in tool_service.get_all_tools() if t.active]
            tool_options = {t.name: t for t in available_tools}
            tool_checks = {}
            
            if available_tools:
                with ui.card().classes('w-full p-3 gap-2 bg-black/20 border-white/5'):
                    ui.label('Tools').classes('text-sm font-bold text-gray-400 mb-1')
                    
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

            # Parameter update logic
            async def update_params():
                if not model_select.value: return
                
                # Update ratings sidebar
                await update_ratings_sidebar(model_select.value)

                with model_select:
                    # Update URL without reload
                    from urllib.parse import quote
                    safe_model = quote(model_select.value)
                    await ui.run_javascript(f"window.history.replaceState(null, '', '/chat?model={safe_model}');")

                    params = await client.get_model_parameters(model_select.value)
                    if 'temperature' in params:
                        temp_slider.value = params['temperature']
                    if 'top_p' in params:
                        top_p_slider.value = params['top_p']
                    if 'repeat_penalty' in params:
                        repeat_penalty_slider.value = params['repeat_penalty']
                    if 'system' in params:
                        system_prompt.value = params['system']
            
            model_select.on_value_change(update_params)
            # Trigger initial update
            if model_select.value:
                asyncio.create_task(update_params())


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

            # Forward declarations 
            async def generate_response(): pass
            async def save_and_respond(msg, new_content): pass

            # Logic Handlers
            def delete_message(msg):
                if msg in messages:
                    messages.remove(msg)
                    app.storage.user['messages'] = messages
                    render_chat_messages.refresh()

            def edit_mode(msg):
                # Reset others editing state
                for m in messages:
                    m['editing'] = False
                msg['editing'] = True
                render_chat_messages.refresh()

            def cancel_edit(msg):
                msg['editing'] = False
                render_chat_messages.refresh()
            
            def save_edit(msg, new_content):
                msg['content'] = new_content
                msg['editing'] = False
                app.storage.user['messages'] = messages
                render_chat_messages.refresh()

            async def rate_message(msg, rating, tag):
                if not msg.get('id'): return
                rating_service.add_rating(
                    model=msg.get('model', 'unknown'),
                    tag=tag,
                    rating=rating,
                    message_id=msg['id']
                )
                ui.notify(f"Rated {rating} stars for {tag}", type='positive')
                await update_ratings_sidebar(msg.get('model', 'unknown'))
                render_chat_messages.refresh()

            async def delete_rating(msg, tag):
                if not msg.get('id'): return
                rating_service.remove_rating(msg['id'], tag)
                ui.notify(f"Removed rating for {tag}", type='info')
                await update_ratings_sidebar(msg.get('model', 'unknown'))
                render_chat_messages.refresh()

            @ui.refreshable
            def render_chat_messages():
                if not messages:
                    return

                for msg in messages:
                    if 'id' not in msg:
                        msg['id'] = str(uuid.uuid4())
                    
                    with ui.column().classes('w-full group'):
                        if msg['role'] == 'user':
                            with ui.row().classes('w-full justify-end items-start gap-2 mb-2'):
                                # Edit/Delete Controls for User
                                with ui.row().classes('opacity-0 group-hover:opacity-100 transition-opacity gap-1 items-center'):
                                     ui.button(icon='edit', on_click=lambda m=msg: edit_mode(m)).props('flat round dense size=sm color=grey')
                                     ui.button(icon='delete', on_click=lambda m=msg: delete_message(m)).props('flat round dense size=sm color=negative')

                                if msg.get('editing', False):
                                    with ui.column().classes('items-end w-full max-w-2xl'):
                                        edit_input = ui.textarea(value=msg['content']).classes('w-full').props('autogrow rows=2')
                                        with ui.row().classes('gap-1 mt-1'):
                                            ui.button('Cancel', on_click=lambda m=msg: cancel_edit(m)).props('flat dense color=grey')
                                            ui.button('Save', on_click=lambda m=msg, inp=edit_input: save_edit(m, inp.value)).props('flat dense color=primary')
                                            ui.button('Respond', on_click=lambda m=msg, inp=edit_input: save_and_respond(m, inp.value)).props('flat dense color=secondary icon=smart_toy')
                                else:
                                    ui.label(msg['content']).classes('text-base px-5 py-3 rounded-2xl bg-[#27272a] text-white max-w-2xl break-words whitespace-pre-wrap')
                                    
                        elif msg['role'] == 'assistant':
                            with ui.row().classes('w-full justify-start gap-4 items-start mb-2'):
                                with ui.avatar(color='transparent', square=True).classes('size-8 shrink-0'):
                                    ui.icon('smart_toy', size='24px').classes('text-indigo-400')
                                
                                with ui.column().classes('gap-2 max-w-3xl flex-grow'):
                                    # Header with model and controls
                                    with ui.row().classes('w-full justify-between items-center'):
                                        ui.label(msg.get('model', 'Unknown Model')).classes('text-xs text-gray-400 font-bold')
                                        # Controls
                                        with ui.row().classes('opacity-0 group-hover:opacity-100 transition-opacity gap-1'):
                                             ui.button(icon='edit', on_click=lambda m=msg: edit_mode(m)).props('flat round dense size=sm color=grey')
                                             ui.button(icon='delete', on_click=lambda m=msg: delete_message(m)).props('flat round dense size=sm color=negative')

                                    if msg.get('editing', False):
                                         with ui.column().classes('w-full'):
                                            edit_input = ui.textarea(value=msg['content']).classes('w-full').props('autogrow rows=5')
                                            with ui.row().classes('gap-1 mt-1'):
                                                ui.button('Cancel', on_click=lambda m=msg: cancel_edit(m)).props('flat dense color=grey')
                                                ui.button('Save', on_click=lambda m=msg, inp=edit_input: save_edit(m, inp.value)).props('flat dense color=primary')
                                    else:
                                        if msg.get('thinking'):
                                            ui.label(msg['thinking']).classes('text-xs text-gray-400 font-mono bg-white/5 p-3 rounded-md border-l-2 border-indigo-500 whitespace-pre-wrap w-full')
                                        
                                        if msg.get('tool_calls'):
                                            with ui.column().classes('gap-1 w-full my-2 bg-orange-900/10 p-2 rounded border border-orange-500/20'):
                                                for tc in msg['tool_calls']:
                                                    fname = tc.get('function', {}).get('name', 'unknown')
                                                    try:
                                                        args = tc.get('function', {}).get('arguments', '')
                                                    except:
                                                        args = '...'
                                                    ui.label(f"🔧 Call: {fname}").classes('text-xs font-mono text-orange-300 font-bold')
                                                    ui.label(str(args)).classes('text-xs font-mono text-orange-200/70 truncate pl-4')

                                        if msg.get('content'):
                                            ui.markdown(msg.get('content', '')).classes('w-full prose dark:prose-invert text-gray-100')
                                        elif msg['role'] == 'assistant' and not msg.get('tool_calls') and not msg.get('thinking'):
                                            ui.label('...').classes('text-gray-500 italic')
                                        
                                        # Rating Controls
                                        if msg.get('id'):
                                            existing_ratings = rating_service.get_ratings_for_message(msg['id'])
                                            
                                            # Existing Ratings Display
                                            if existing_ratings:
                                                with ui.row().classes('gap-2 mt-2'):
                                                    for r in existing_ratings:
                                                        with ui.row().classes('items-center gap-1 bg-yellow-400/10 px-2 py-1 rounded border border-yellow-400/20'):
                                                            ui.label(f"{r.tag}: {r.rating}★").classes('text-xs font-bold text-yellow-400')
                                                            ui.icon('close', size='xs').classes('text-yellow-400/50 cursor-pointer hover:text-red-400').on('click', lambda _, m=msg, t=r.tag: delete_rating(m, t))
                                            
                                            # Rating Input (Only show if not processing for cleaner UI? Or always?)
                                            # Always show for history
                                            with ui.row().classes('items-center gap-2 mt-2 opacity-50 hover:opacity-100 transition-opacity'):
                                                available_tags = config_manager.get_rating_tags()
                                                default_tag = available_tags[0] if available_tags else "General"
                                                
                                                tag_select = ui.select(options=available_tags, value=default_tag).props('dense options-dense borderless').classes('w-24 text-xs')
                                                
                                                with ui.row().classes('gap-0'):
                                                    for i in range(1, 6):
                                                        ui.button(icon='star', 
                                                                  on_click=lambda s=i, t=tag_select, m=msg: rate_message(m, s, t.value)
                                                                 ).props(f'flat round dense size=sm color={"orange" if existing_ratings and existing_ratings[0].rating >= i else "grey"}').classes('text-xs') # logic for color is simple, mainly for interaction
                                                
                                                # Improved star UI: using toggle or just buttons. Buttons are easiest for immediate action.
                                                # Let's make them always grey unless hovered or rated?
                                                # For simplicity in this iteration: Just buttons. 
                                                # To reflect "current" rating in buttons requires complexity. 
                                                # Let's just have clickable stars.
                        
                        elif msg['role'] == 'tool':
                             with ui.row().classes('w-full justify-start gap-4 items-start mb-2'):
                                with ui.avatar(color='transparent', square=True).classes('size-8 shrink-0'):
                                    ui.icon('output', size='20px').classes('text-gray-500')
                                with ui.column().classes('gap-1 max-w-3xl flex-grow'):
                                    ui.label(f"Tool Output: {msg.get('name', 'unknown')}").classes('text-xs text-gray-500 font-bold')
                                    ui.label(msg['content']).classes('text-xs font-mono bg-white/5 p-2 rounded text-gray-300 whitespace-pre-wrap')

            
            with chat_container:
                render_chat_messages()
                # Placeholder for streaming
                streaming_container = ui.column().classes('w-full')


            # Scroll init
            if messages:
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
                    with chat_container:
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
                                # Sometimes tool_calls in storage are raw dicts, simple pass through
                                api_messages.append(clean_msg)
                        
                        # Conversation Loop
                        while True:
                            response_content = ""
                            full_thinking = ""
                            tool_calls = []
                            
                            # UI Setup
                            with streaming_container:
                                response_row = ui.row().classes('w-full justify-start gap-4 items-start mb-2')
                                with response_row:
                                   with ui.avatar(color='transparent', square=True).classes('size-8 shrink-0'):
                                        ui.icon('smart_toy', size='24px').classes('text-indigo-400')
                                   
                                   response_col = ui.column().classes('gap-2 max-w-3xl flex-grow')
                                   with response_col:
                                        ui.label(model_select.value).classes('text-xs text-gray-400 font-bold')
                                        spinner = ui.spinner('dots', size='sm').classes('text-indigo-400')
                                        thinking_label = ui.label('').classes('hidden text-xs text-gray-400 font-mono bg-white/5 p-3 rounded-md border-l-2 border-indigo-500 whitespace-pre-wrap w-full')
                                        response_markdown = ui.markdown('').classes('w-full prose dark:prose-invert text-gray-100')
                                        tool_calls_label = ui.label('').classes('hidden text-xs font-mono text-orange-300 w-full whitespace-pre-wrap')
    
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
                                
                                spinner.delete()
                                
                                async for chunk in stream:
                                    if state['stopping']:
                                        if not response_content and not full_thinking:
                                            response_markdown.content = '_Stopped by user_'
                                        break
    
                                    msg_chunk = chunk.get('message', {})
                                    part = msg_chunk.get('content') or ''
                                    thinking_part = msg_chunk.get('thinking', '')
                                    tool_calls_part = msg_chunk.get('tool_calls', [])
                                    
                                    if thinking_part:
                                        full_thinking += thinking_part
                                        thinking_label.text = full_thinking
                                        thinking_label.classes(remove='hidden')
                                    
                                    if tool_calls_part:
                                        tool_calls.extend(tool_calls_part)
                                        names = [tc.get('function', {}).get('name', 'unknown') for tc in tool_calls]
                                        tool_calls_label.text = f"Tool Calls: {', '.join(names)}"
                                        tool_calls_label.classes(remove='hidden')
                                    
                                    if part:
                                        response_content += part
                                        response_markdown.content = response_content
                                        
                                    response_markdown.update()
                                    await scroll_to_bottom(check_position=True)
                                    
                                # Loop Finishes (chunk stream done)
                                streaming_container.clear()
                                
                                # Save Assistant Message
                                assistant_msg = {
                                    'role': 'assistant', 
                                    'content': response_content, 
                                    'thinking': full_thinking, 
                                    'model': model_select.value,
                                    'id': str(uuid.uuid4())
                                }
                                if tool_calls:
                                    assistant_msg['tool_calls'] = tool_calls
                                
                                messages.append(assistant_msg)
                                
                                # Clean version for API
                                clean_assist = {k:v for k,v in assistant_msg.items() if k in ['role', 'content', 'tool_calls']}
                                api_messages.append(clean_assist) 

                                app.storage.user['messages'] = messages
                                render_chat_messages.refresh()
                                await scroll_to_bottom(check_position=True)

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
                                    
                                    app.storage.user['messages'] = messages
                                    render_chat_messages.refresh()
                                    await scroll_to_bottom(check_position=True)
                                    # Continue loop to send tool output back to model
                                else:
                                    break # No tools, conversation turn ends

                            except Exception as e:
                                try:
                                    spinner.delete()
                                except: pass
                                ui.notify(f'Error: {e}', type='negative')
                                streaming_container.clear()
                                break
                        
                        state['processing'] = False
                        state['stopping'] = False
                        update_button_state()

                # --- User Action Handlers ---
                async def save_and_respond(msg, new_content):
                    msg['content'] = new_content
                    msg['editing'] = False
                    
                    # Truncate history after this message
                    try:
                        idx = messages.index(msg)
                        del messages[idx+1:]
                    except ValueError:
                        pass
                    
                    app.storage.user['messages'] = messages
                    render_chat_messages.refresh()
                    # Run generation in background to avoid context issues with deleted button
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
                    render_chat_messages.refresh()
                    await scroll_to_bottom()
                    
                    await generate_response()

                user_input.on('keydown.enter.exact',
                    lambda e: send_message() if not e.args['shiftKey'] else None, 
                    args=['shiftKey']
                )
                send_btn = ui.button(icon='send', on_click=send_message).props('flat round color=primary')
            
        # Keyboard submit
        # This is a bit tricky with textarea autogrow, usually shift+enter for new line
        # but just enter for submit requires key handler. NiceGUI 2.0 has handy handlers.
        # Simple version: Button only or key listener.
