from nicegui import ui, app
from utils.ollama_client import client
import asyncio

async def create_page(model_param: str = None):
    # Add custom CSS for <think> tags
    # Custom CSS for <think> tags removed as per user request

    
    # Use the passed parameter
    query_model = model_param
    # State
    messages = []
    state = {'processing': False, 'stopping': False}
    
    # Layout using a row for sidebar + chat
    with ui.row().classes('w-full max-w-[1200px] mx-auto h-[calc(100vh-3rem)] pt-14 px-4 gap-6 items-stretch'):
        
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
            # Chat Area
            chat_container = ui.column().classes('w-full flex-grow overflow-y-auto p-4 gap-4 rounded-lg bg-black/20 border border-white/5').props('id=chat-scroll-area')

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

                async def send_message():
                    if state['processing']:
                        state['stopping'] = True
                        update_button_state()
                        return

                    content = user_input.value.strip()
                    if not content or not model_select.value: return
                    
                    state['processing'] = True
                    state['stopping'] = False
                    update_button_state()
                    
                    user_input.value = ''
                    
                    # Setup messages for API
                    api_messages = []
                    if system_prompt.value:
                        api_messages.append({'role': 'system', 'content': system_prompt.value})
                    
                    # Add history
                    for msg in messages:
                        clean_msg = {k:v for k,v in msg.items() if k in ['role', 'content', 'images']}
                        api_messages.append(clean_msg)
                    
                    # Add current user message
                    api_messages.append({'role': 'user', 'content': content})
                    messages.append({'role': 'user', 'content': content})

                    # Display User Message
                    with chat_container:
                        with ui.row().classes('w-full justify-end mb-2'):
                            ui.label(content).classes('text-base px-5 py-3 rounded-2xl bg-[#27272a] text-white max-w-2xl break-words whitespace-pre-wrap')
                    
                    # Placeholder for AI Message
                    with chat_container:
                         response_row = ui.row().classes('w-full justify-start gap-4 items-start mb-2')
                         with response_row:
                            with ui.avatar(color='transparent', square=True).classes('size-8 shrink-0'):
                                 ui.icon('smart_toy', size='24px').classes('text-indigo-400')
                            
                            response_col = ui.column().classes('gap-2 max-w-3xl flex-grow')
                            with response_col:
                                 spinner = ui.spinner('dots', size='sm').classes('text-indigo-400')
                                 thinking_label = ui.label('').classes('hidden text-xs text-gray-400 font-mono bg-white/5 p-3 rounded-md border-l-2 border-indigo-500 whitespace-pre-wrap w-full')
                                 response_markdown = ui.markdown('')
                    
                    async def scroll_to_bottom():
                        await ui.run_javascript('var el = document.getElementById("chat-scroll-area"); if (el) el.scrollTop = el.scrollHeight;')
                    
                    await scroll_to_bottom()

                    # Streaming Response
                    response_content = ""
                    full_thinking = ""
                    
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
                            
                        messages.append({'role': 'assistant', 'content': response_content, 'thinking': full_thinking})
                        await scroll_to_bottom()
                        
                    except Exception as e:
                        spinner.delete()
                        ui.notify(f'Error: {e}', type='negative')
                    finally:
                        state['processing'] = False
                        state['stopping'] = False
                        update_button_state()

                user_input.on('keydown.ctrl.enter', lambda: send_message())
                send_btn = ui.button(icon='send', on_click=send_message).props('flat round color=primary')
            
        # Keyboard submit
        # This is a bit tricky with textarea autogrow, usually shift+enter for new line
        # but just enter for submit requires key handler. NiceGUI 2.0 has handy handlers.
        # Simple version: Button only or key listener.
