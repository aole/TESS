from nicegui import ui, app
from utils.ollama_client import client
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
    
    # Layout using a row for sidebar + chat
    with ui.row().classes('w-full max-w-[1200px] mx-auto h-[calc(100vh-3rem)] pt-14 px-4 gap-6 items-stretch flex-nowrap'):
        
        # --- Left Sidebar (Controls) ---
        with ui.column().classes('w-72 shrink-0 gap-4'):
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
                
                system_prompt = ui.textarea(label='System Prompt', placeholder='You are a helpful assistant...').classes('w-full text-sm').props('rows=5')
                
                def clear_chat():
                    messages.clear()
                    app.storage.user['messages'] = []
                    render_chat_messages.refresh()
                
                ui.button('Clear Chat', on_click=clear_chat).props('outline color=negative').classes('w-full mt-2')

            # Parameter update logic
            async def update_params():
                if not model_select.value: return
                
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
            
            model_select.on_value_change(update_params)
            # Trigger initial update
            if model_select.value:
                asyncio.create_task(update_params())


        # --- Right Area (Chat) ---
        with ui.column().classes('flex-grow h-full gap-2 relative min-w-0'):
            chat_container = ui.column().classes('w-full flex-grow overflow-y-auto p-4 gap-4 rounded-lg bg-black/20 border border-white/5').props('id=chat-scroll-area')
            
            async def scroll_to_bottom():
                await ui.run_javascript('var el = document.getElementById("chat-scroll-area"); if (el) el.scrollTop = el.scrollHeight;')

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
                                        ui.markdown(msg.get('content', ''))

            
            with chat_container:
                render_chat_messages()
                # Placeholder for streaming
                streaming_container = ui.column().classes('w-full')


            # Scroll init
            if messages:
                ui.run_javascript('var el = document.getElementById("chat-scroll-area"); if (el) el.scrollTop = el.scrollHeight;')

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
                        
                        # Prepare messages
                        api_messages = []
                        if system_prompt.value:
                            api_messages.append({'role': 'system', 'content': system_prompt.value})
                        
                        for msg in messages:
                            if msg['role'] in ['user', 'assistant']:
                                clean_msg = {k:v for k,v in msg.items() if k in ['role', 'content', 'images']}
                                api_messages.append(clean_msg)
                        
                        # Streaming Response Setup
                        response_content = ""
                        full_thinking = ""
                        
                        # Temporary UI
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
                                    response_markdown = ui.markdown('')

                        await scroll_to_bottom()

                        try:
                            stream = await client.chat(
                                model=model_select.value,
                                messages=api_messages,
                                stream=True,
                                options={
                                    'temperature': temp_slider.value,
                                    'top_p': top_p_slider.value
                                }
                            )
                            
                            spinner.delete()
                            
                            async for chunk in stream:
                                if state['stopping']:
                                    if not response_content and not full_thinking:
                                        response_markdown.content = '_Stopped by user_'
                                    break

                                msg_chunk = chunk.get('message', {})
                                part = msg_chunk.get('content', '')
                                thinking_part = msg_chunk.get('thinking', '')
                                
                                if thinking_part:
                                    full_thinking += thinking_part
                                    thinking_label.text = full_thinking
                                    thinking_label.classes(remove='hidden')
                                else:
                                    response_content += part
                                    response_markdown.content = response_content
                                
                                await scroll_to_bottom()
                                
                            # Finalize
                            streaming_container.clear()
                            
                            assistant_msg = {
                                'role': 'assistant', 
                                'content': response_content, 
                                'thinking': full_thinking, 
                                'model': model_select.value,
                                'id': str(uuid.uuid4())
                            }
                            messages.append(assistant_msg)
                            app.storage.user['messages'] = messages
                            render_chat_messages.refresh()
                            await scroll_to_bottom()
                            
                        except Exception as e:
                            try:
                                spinner.delete()
                            except:
                                pass
                            ui.notify(f'Error: {e}', type='negative')
                            streaming_container.clear()
                        finally:
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

                user_input.on('keydown.ctrl.enter', lambda: send_message())
                send_btn = ui.button(icon='send', on_click=send_message).props('flat round color=primary')
            
        # Keyboard submit
        # This is a bit tricky with textarea autogrow, usually shift+enter for new line
        # but just enter for submit requires key handler. NiceGUI 2.0 has handy handlers.
        # Simple version: Button only or key listener.
