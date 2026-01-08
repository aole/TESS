from nicegui import ui
from utils.ollama_client import client
from utils.config import config_manager
import asyncio

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
            chat1 = ui.column().classes('h-full glass-panel rounded p-2 overflow-y-auto border border-white/10').props('id=arena-scroll-1')
            with chat1:
                ui.label('Model 1 Output').classes('text-xs text-muted mb-1')
            
            # Area 2
            chat2 = ui.column().classes('h-full glass-panel rounded p-2 overflow-y-auto border border-white/10').props('id=arena-scroll-2')
            with chat2:
                ui.label('Model 2 Output').classes('text-xs text-muted mb-1')

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
                
                with chat1:
                    ui.chat_message(content, name='User', sent=True)
                with chat2:
                    ui.chat_message(content, name='User', sent=True)
                
                await scroll_to_bottom('arena-scroll-1')
                await scroll_to_bottom('arena-scroll-2')

                # Prepare Messages
                msgs = []
                if system_prompt.value:
                    msgs.append({'role': 'system', 'content': system_prompt.value})
                msgs.append({'role': 'user', 'content': content})

                # Run Model 1
                with chat1:
                    msg1 = ui.chat_message(name=model1, sent=False)
                    spinner1 = ui.spinner('dots')
                
                output1 = ""
                try:
                    # Async streaming
                    stream1 = await client.chat(model=model1, messages=msgs, stream=True, keep_alive=0, log_requests=config_manager.is_logging_enabled('arena'))
                    spinner1.delete()
                    async for chunk in stream1:
                        if state['stopping']:
                            if not output1:
                                msg1.clear()
                                with msg1: ui.markdown('_Stopped_')
                                await scroll_to_bottom('arena-scroll-1', check_position=True)
                            break
                        part = chunk.get('message', {}).get('content', '')
                        output1 += part
                        msg1.clear()
                        with msg1:
                            ui.markdown(output1)
                        await scroll_to_bottom('arena-scroll-1', check_position=True)
                        # No sleep needed with async iterator usually, but good for UI responsiveness
                        # await asyncio.sleep(0) 
                except Exception as e:
                    spinner1.delete()
                    ui.notify(f'Model 1 Error: {e}', type='negative')

                # Run Model 2 (Sequential) - only if not stopped
                if not state['stopping']:
                    # Give a breather for offloading
                    await asyncio.sleep(1.0)
                    
                    with chat2:
                        msg2 = ui.chat_message(name=model2, sent=False)
                        spinner2 = ui.spinner('dots')
                    
                    output2 = ""
                    try:
                        stream2 = await client.chat(model=model2, messages=msgs, stream=True, keep_alive=0, log_requests=config_manager.is_logging_enabled('arena'))
                        spinner2.delete()
                        async for chunk in stream2:
                            if state['stopping']:
                                if not output2:
                                   msg2.clear()
                                   with msg2: ui.markdown('_Stopped_')
                                   await scroll_to_bottom('arena-scroll-2', check_position=True)
                                break
                            part = chunk.get('message', {}).get('content', '')
                            output2 += part
                            msg2.clear()
                            with msg2:
                                ui.markdown(output2)
                            await scroll_to_bottom('arena-scroll-2', check_position=True)
                    except Exception as e:
                        spinner2.delete()
                        ui.notify(f'Model 2 Error: {e}', type='negative')
                
                state['processing'] = False
                state['stopping'] = False
                update_btn()

            user_input.on('keydown.enter.prevent.exact', run_battle)
            send_btn = ui.button(icon='send', on_click=run_battle).props('flat round color=primary')
