from nicegui import ui
from utils.ollama_client import client
from utils.config import config_manager
from utils.chat_renderer import ConversationRenderer
import asyncio
import uuid

async def create_page():
    
    async def scroll_to_bottom(area_id, check_position=False):
        js = """
        var el = document.getElementById("AREA_ID");
        if (el) {
            if (typeof window.isArenaAtBottom === 'undefined') {
                window.isArenaAtBottom = {};
            }
            if (!el.dataset.hasScrollListener) {
                el.dataset.hasScrollListener = "true";
                el.addEventListener('scroll', function() {
                        window.isArenaAtBottom["AREA_ID"] = (el.scrollHeight - el.scrollTop - el.clientHeight) < 50;
                });
            }
            if (!CHECK_POSITION) {
                el.scrollTop = el.scrollHeight;
                window.isArenaAtBottom["AREA_ID"] = true;
            } else if (window.isArenaAtBottom["AREA_ID"]) {
                    el.scrollTop = el.scrollHeight;
            }
        }
        """.replace('AREA_ID', area_id).replace('CHECK_POSITION', 'true' if check_position else 'false')
        await ui.run_javascript(js)

    # Layout
    with ui.column().classes('w-full h-[calc(100vh-3rem)] pt-14 px-4 gap-2'):
        
        # Data Loading
        try:
            models_data = await client.list_models()
            model_options = [m['model'] for m in models_data]
        except Exception as e:
            ui.notify(f'Failed to load models: {e}', type='negative')
            model_options = []

        # Controls Row
        with ui.row().classes('w-full gap-2 items-start'):
            default_model1 = model_options[0] if len(model_options) > 0 else None
            default_model2 = model_options[1] if len(model_options) > 1 else default_model1

            # Model 1 Selector
            model1_select = ui.select(
                options=model_options,
                label='Model 1',
                value=default_model1
            ).props('dense options-dense').classes('w-1/3 glass-panel px-2 rounded')

            # Model 2 Selector
            model2_select = ui.select(
                options=model_options,
                label='Model 2',
                value=default_model2
            ).props('dense options-dense').classes('w-1/3 glass-panel px-2 rounded')

        # System Prompt
        system_prompt = ui.textarea(label='Shared System Prompt', placeholder='You are a helpful assistant...').props('dense rows=1').classes('w-full glass-panel px-2 rounded')

        # Chat Areas (Side by Side)
        with ui.grid(columns=2).classes('w-full flex-grow gap-2'):
            # Area 1
            chat1 = ui.column().classes('h-full w-full overflow-y-auto p-4 gap-4 rounded-lg bg-black/20 border border-white/5').props('id=arena-scroll-1')
            with chat1:
                ui.label('Model 1 Output').classes('text-xs text-muted mb-1')
            
            # Area 2
            chat2 = ui.column().classes('h-full w-full overflow-y-auto p-4 gap-4 rounded-lg bg-black/20 border border-white/5').props('id=arena-scroll-2')
            with chat2:
                ui.label('Model 2 Output').classes('text-xs text-muted mb-1')

        # Initialize Renderers
        # Arena doesn't currently support editing/ratings, so we don't pass callbacks.
        renderer1 = ConversationRenderer(chat1, show_avatars=True)
        renderer2 = ConversationRenderer(chat2, show_avatars=True)

        # Message State (Ephemeral for now)
        messages1 = []
        messages2 = []

        # Input Area
        with ui.row().classes('w-full items-end gap-2 p-2 glass-panel rounded-lg'):
            user_input = ui.textarea(placeholder='Type a message for both models...').classes('w-full flex-grow').props('autogrow bg-color=transparent borderless dense rows=1')
            
            # Forward declaration
            send_btn = None
            state = {'processing': False, 'stopping': False}

            def update_btn():
                 if not send_btn: return
                 if state['processing']:
                     if state['stopping']:
                         send_btn.props('icon=hourglass_empty color=warning')
                     else:
                         send_btn.props('icon=stop color=negative')
                 else:
                     send_btn.props('icon=send color=primary')

            async def run_battle():
                if state['processing']:
                    state['stopping'] = True
                    update_btn()
                    return

                content = user_input.value
                model1 = model1_select.value
                model2 = model2_select.value
                
                if not content or not model1 or not model2:
                    ui.notify('Please select both models and enter a prompt.', type='warning')
                    return
                
                state['processing'] = True
                state['stopping'] = False
                update_btn()

                user_input.value = ''
                
                # Render User Message
                user_msg_id = str(uuid.uuid4())
                user_msg = {'id': user_msg_id, 'role': 'user', 'content': content}
                
                # Append to both histories
                messages1.append(user_msg.copy()) # Copy to ensure distinct identity if we ever modify in place
                messages2.append(user_msg.copy())

                renderer1.render_message(user_msg)
                renderer2.render_message(user_msg)
                
                await scroll_to_bottom('arena-scroll-1')
                await scroll_to_bottom('arena-scroll-2')

                # Prepare context for API
                # Common system prompt
                sys_msg = {'role': 'system', 'content': system_prompt.value} if system_prompt.value else None

                api_msgs1 = []
                if sys_msg: api_msgs1.append(sys_msg)
                api_msgs1.extend([{'role': m['role'], 'content': m['content']} for m in messages1])

                api_msgs2 = []
                if sys_msg: api_msgs2.append(sys_msg)
                api_msgs2.extend([{'role': m['role'], 'content': m['content']} for m in messages2])


                # --- Run Model 1 ---
                msg1_id = str(uuid.uuid4())
                msg1 = {
                    'id': msg1_id, 
                    'role': 'assistant', 
                    'model': model1, 
                    'content': '', 
                    'thinking': '',
                    'tool_calls': [] 
                }
                messages1.append(msg1)
                renderer1.render_message(msg1)
                await scroll_to_bottom('arena-scroll-1')
                
                full_content1 = ""
                full_thinking1 = ""
                
                try:
                    stream1 = await client.chat(model=model1, messages=api_msgs1, stream=True, keep_alive=0, log_requests=config_manager.is_logging_enabled('arena'))
                    
                    async for chunk in stream1:
                        if state['stopping']:
                            if not full_content1 and not full_thinking1:
                                full_content1 = '_Stopped_'
                                await renderer1.update_message(msg1_id, full_content1, full_thinking1, [])
                            break

                        msg_chunk = chunk.get('message', {})
                        part = msg_chunk.get('content') or ''
                        thinking_part = msg_chunk.get('thinking', '')
                        
                        if thinking_part:
                            full_thinking1 += thinking_part
                        if part:
                            full_content1 += part
                        
                        await renderer1.update_message(msg1_id, full_content1, full_thinking1, [])
                        await scroll_to_bottom('arena-scroll-1', check_position=True)

                    # Finalize Msg 1
                    msg1['content'] = full_content1
                    msg1['thinking'] = full_thinking1

                except Exception as e:
                    ui.notify(f'Model 1 Error: {e}', type='negative')
                    # Could update message to show error
                    await renderer1.update_message(msg1_id, full_content1 + f"\n\n*Error: {e}*", full_thinking1, [])

                # --- Run Model 2 ---
                if not state['stopping']:
                    await asyncio.sleep(1.0) # Breather
                    
                    msg2_id = str(uuid.uuid4())
                    msg2 = {
                        'id': msg2_id, 
                        'role': 'assistant', 
                        'model': model2, 
                        'content': '', 
                        'thinking': '',
                        'tool_calls': []
                    }
                    messages2.append(msg2)
                    renderer2.render_message(msg2)
                    await scroll_to_bottom('arena-scroll-2')

                    full_content2 = ""
                    full_thinking2 = ""

                    try:
                        stream2 = await client.chat(model=model2, messages=api_msgs2, stream=True, keep_alive=0, log_requests=config_manager.is_logging_enabled('arena'))
                        
                        async for chunk in stream2:
                            if state['stopping']:
                                if not full_content2 and not full_thinking2:
                                    full_content2 = '_Stopped_'
                                    await renderer2.update_message(msg2_id, full_content2, full_thinking2, [])
                                break

                            msg_chunk = chunk.get('message', {})
                            part = msg_chunk.get('content') or ''
                            thinking_part = msg_chunk.get('thinking', '')
                            
                            if thinking_part:
                                full_thinking2 += thinking_part
                            if part:
                                full_content2 += part
                            
                            await renderer2.update_message(msg2_id, full_content2, full_thinking2, [])
                            await scroll_to_bottom('arena-scroll-2', check_position=True)
                        
                        # Finalize Msg 2
                        msg2['content'] = full_content2
                        msg2['thinking'] = full_thinking2

                    except Exception as e:
                        ui.notify(f'Model 2 Error: {e}', type='negative')
                        await renderer2.update_message(msg2_id, full_content2 + f"\n\n*Error: {e}*", full_thinking2, [])
                
                state['processing'] = False
                state['stopping'] = False
                update_btn()

            user_input.on('keydown.enter.prevent.exact', run_battle)
            send_btn = ui.button(icon='send', on_click=run_battle).props('flat round color=primary')
