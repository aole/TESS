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
    
    # Layout using a column for the whole page
    with ui.column().classes('w-full h-[calc(100vh-3rem)] pt-14 px-4 relative gap-0'):
        # Header Row: Model Selector + Params
        with ui.row().classes('w-full justify-between items-start mb-2 gap-2'):
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
            
            model_select = ui.select(
                options=model_options,
                label='Model',
                value=default_model,
            ).props('dense options-dense').classes('w-48 glass-panel px-2 rounded')

            with ui.row().classes('gap-2 items-center'):
                with ui.expansion('Parameters').classes('glass-panel rounded px-2 py-0'):
                    with ui.column().classes('gap-1 p-2 w-64'):
                        temp_slider = ui.slider(min=0, max=1, step=0.1, value=0.7).props('label-always thumb-path=""')
                        ui.label('Temperature').classes('text-xs text-muted')
                        
                        top_p_slider = ui.slider(min=0, max=1, step=0.1, value=0.9).props('label-always')
                        ui.label('Top P').classes('text-xs text-muted')
                        
                        system_prompt = ui.textarea(label='System Prompt', placeholder='You are a helpful assistant...').classes('w-full')

            # Parameter update logic
            async def update_params():
                if not model_select.value: return
                params = await client.get_model_parameters(model_select.value)
                if 'temperature' in params:
                    temp_slider.value = params['temperature']
                if 'top_p' in params:
                    top_p_slider.value = params['top_p']
            
            model_select.on_value_change(update_params)
            # Trigger initial update
            if model_select.value:
                asyncio.create_task(update_params())

        # Chat Area (Flex grow to fill space)
        chat_container = ui.column().classes('w-full flex-grow overflow-y-auto p-2 gap-2 rounded-lg bg-black/20 mb-2 border border-white/5')

        # Input Area (Fixed at bottom)
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
                    # Filter out internal keys
                    clean_msg = {k:v for k,v in msg.items() if k in ['role', 'content', 'images']}
                    api_messages.append(clean_msg)
                
                # Add current user message
                api_messages.append({'role': 'user', 'content': content})
                messages.append({'role': 'user', 'content': content})

                # Display User Message
                with chat_container:
                    ui.chat_message(content, name='User', sent=True)
                
                # Placeholder for AI Message
                with chat_container:
                     response_message = ui.chat_message(name=model_select.value, sent=False)
                     spinner = ui.spinner('dots')
                
                await ui.run_javascript(f'window.scrollTo(0, document.body.scrollHeight)')

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
                            if not response_content:
                                response_message.clear()
                                with response_message:
                                    ui.markdown('_Stopped by user_')
                            break

                        msg_chunk = chunk.get('message', {})
                        part = msg_chunk.get('content', '')
                        thinking_part = msg_chunk.get('thinking', '')
                        
                        if thinking_part:
                            full_thinking += thinking_part
                        else:
                            response_content += part
                        
                        response_message.clear()
                        with response_message:
                            if full_thinking:
                                # Use ui.label for raw text control, preventing markdown interference
                                ui.label(full_thinking).classes('text-xs text-darkgray-400 font-mono mb-2 bg-white/5 p-2 rounded border-l-2 border-gray-600 whitespace-pre-wrap w-full')
                            
                            if response_content:
                                ui.markdown(response_content)
                        
                    messages.append({'role': 'assistant', 'content': response_content, 'thinking': full_thinking})
                    await ui.run_javascript(f'window.scrollTo(0, document.body.scrollHeight)')
                    
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
