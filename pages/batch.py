from nicegui import ui
from utils.ollama_client import client
from utils.config import config_manager
from utils.chat_renderer import ConversationRenderer
import asyncio
import time
import uuid

async def create_page():
    
    async def scroll_to_bottom(area_id, check_position=False):
        js = """
        var el = document.getElementById("AREA_ID");
        if (el) {
            if (typeof window.isBatchAtBottom === 'undefined') {
                window.isBatchAtBottom = {};
            }
            if (!el.dataset.hasScrollListener) {
                el.dataset.hasScrollListener = "true";
                el.addEventListener('scroll', function() {
                        window.isBatchAtBottom["AREA_ID"] = (el.scrollHeight - el.scrollTop - el.clientHeight) < 50;
                });
            }
            if (!CHECK_POSITION) {
                el.scrollTop = el.scrollHeight;
                window.isBatchAtBottom["AREA_ID"] = true;
            } else if (window.isBatchAtBottom["AREA_ID"]) {
                    el.scrollTop = el.scrollHeight;
            }
        }
        """.replace('AREA_ID', area_id).replace('CHECK_POSITION', 'true' if check_position else 'false')
        await ui.run_javascript(js)

    # Layout
    with ui.column().classes('w-full h-full pt-14 px-4 max-w-7xl mx-auto'):
        # Header with Toggle
        with ui.row().classes('w-full justify-between items-center mb-2'):
            ui.label('Batch Processing').classes('text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-cyan-400')
            toggle_btn = ui.button(icon='expand_less').props('flat round dense text-color=grey')

        # Data Loading
        try:
             models_data = await client.list_models()
             all_models = [m['model'] for m in models_data]
        except Exception as e:
             ui.notify(f"Error loading models: {e}", type='negative')
             all_models = []

        # Selection & Prompts
        config_section = ui.row().classes('w-full gap-4 items-start flex-nowrap')
        
        def toggle_config():
            config_section.visible = not config_section.visible
            toggle_btn.props(f'icon={"expand_more" if not config_section.visible else "expand_less"}')
        
        toggle_btn.on_click(toggle_config)

        with config_section:
            # Model Selection
            with ui.card().classes('w-1/3 min-w-[300px] glass-panel p-4'):
                model_toggles = {}
                
                def toggle_all(value):
                    for t in model_toggles.values():
                        t.value = value

                with ui.row().classes('w-full justify-between items-center mb-4'):
                    ui.label('Select Models').classes('text-lg font-bold')
                    with ui.row().classes('gap-1'):
                        ui.button('All', on_click=lambda: toggle_all(True)).props('dense flat size=sm color=secondary')
                        ui.button('None', on_click=lambda: toggle_all(False)).props('dense flat size=sm text-color=grey')
                
                with ui.scroll_area().classes('h-64 pr-4'):
                    for m in all_models:
                        t = ui.checkbox(m).props('dense color=secondary')
                        model_toggles[m] = t

            # Prompts Area
            with ui.column().classes('flex-1 gap-2 min-w-0'):
                system_prompt = ui.textarea(label='System Prompt', placeholder='You are...').props('dense rows=1').classes('w-full glass-panel px-4 rounded')
                user_prompt = ui.textarea(label='User Prompt', placeholder='Tell me a joke...').props('dense rows=2').classes('w-full glass-panel px-4 rounded')
                
                start_time = time.time()
                
                # State
                state = {'processing': False, 'stopping': False}
                run_btn = None

                def update_btn():
                    if not run_btn: return
                    if state['processing']:
                        if state['stopping']:
                            run_btn.props('color=warning icon=hourglass_empty')
                            run_btn.set_text('Stopping...')
                        else:
                            run_btn.props('color=negative icon=stop')
                            run_btn.set_text('Stop Batch')
                    else:
                        run_btn.props('color=primary icon=play_arrow')
                        run_btn.set_text('Run Batch')

                async def run_batch():
                    if state['processing']:
                        state['stopping'] = True
                        update_btn()
                        return

                    # Get selected models
                    targets = [name for name, toggle in model_toggles.items() if toggle.value]
                    if not targets:
                        ui.notify('Select at least one model', type='warning')
                        return
                    if not user_prompt.value:
                        ui.notify('Enter a prompt', type='warning')
                        return
                    
                    state['processing'] = True
                    state['stopping'] = False
                    update_btn()

                    # Clear previous results
                    results_container.clear()
                    
                    # Prepare messages
                    msgs = []
                    if system_prompt.value:
                        msgs.append({'role': 'system', 'content': system_prompt.value})
                    msgs.append({'role': 'user', 'content': user_prompt.value})

                    # Create Tabs structure
                    with results_container:
                        tabs = ui.tabs().classes('w-full text-teal-400')
                        panels = ui.tab_panels(tabs, value=targets[0]).classes('w-full rounded-b-lg bg-black/20 border border-white/5 min-h-[300px]')
                        
                        # Create tab header and panels
                        model_tabs = {}
                        model_panels = {}
                        model_renderers = {} # Map model -> renderer
                        model_metrics = {}
                        model_scroll_ids = {}
                        
                        with tabs:
                            for model in targets:
                                t = ui.tab(model)
                                model_tabs[model] = t
                        
                        with panels:
                            for model in targets:
                                with ui.tab_panel(model).classes('h-[60vh] p-0'):
                                    uid = f"batch-res-{uuid.uuid4()}"
                                    model_scroll_ids[model] = uid
                                    with ui.column().classes('w-full h-full overflow-y-auto p-4 gap-4').props(f'id={uid}'):
                                        # Metrics Row
                                        with ui.row().classes('w-full items-center gap-4 mb-2 text-xs text-gray-400 font-mono border-b border-gray-700 pb-2'):
                                            model_metrics[model] = ui.label('Waiting...')
                                        
                                        # Renderer Container
                                        renderer_container = ui.column().classes('w-full flex-grow')
                                        model_renderers[model] = ConversationRenderer(renderer_container)
                                        
                                        # Render User Message immediately to show what's being processed
                                        user_msg = {'role': 'user', 'content': user_prompt.value}
                                        model_renderers[model].render_message(user_msg)


                    # Sequential Execution
                    for model in targets:
                        if state['stopping']:
                            model_metrics[model].set_text('Cancelled')
                            break
                        
                        # Switch tab to current model
                        tabs.set_value(model)
                        
                        renderer = model_renderers[model]
                        metrics_label = model_metrics[model]
                        
                        metrics_label.set_text('Generating...')
                        
                        # Create Assistant Message Placeholder
                        msg_id = str(uuid.uuid4())
                        assistant_msg = {
                            'id': msg_id,
                            'role': 'assistant',
                            'model': model,
                            'content': '',
                            'thinking': '',
                            'tool_calls': []
                        }
                        renderer.render_message(assistant_msg)
                        
                        output = ""
                        thinking = ""
                        token_count = 0
                        t0 = time.time()
                        
                        try:
                            stream = await client.chat(model=model, messages=msgs, stream=True, keep_alive=0, log_requests=config_manager.is_logging_enabled('batch'))
                            async for chunk in stream:
                                if state['stopping']:
                                    output += '\n\n_Stopped_'
                                    await renderer.update_message(msg_id, output, thinking, [])
                                    await scroll_to_bottom(model_scroll_ids[model], check_position=True)
                                    await stream.aclose()
                                    break
                                
                                msg_chunk = chunk.get('message', {})
                                val = msg_chunk.get('content', '')
                                thk = msg_chunk.get('thinking', '')
                                tool_calls_part = msg_chunk.get('tool_calls', []) # batch usually ignores tools but good to have
                                
                                # Update Stats if available in chunk
                                if 'eval_count' in chunk:
                                    token_count = chunk['eval_count']
                                
                                if thk:
                                    thinking += thk
                                
                                if val:
                                    output += val
                                
                                await renderer.update_message(msg_id, output, thinking, []) # ignoring tools for batch unless needed
                                await scroll_to_bottom(model_scroll_ids[model], check_position=True)
                            
                            duration = time.time() - t0
                            # Final metrics update
                            metrics_label.set_text(f"Time: {duration:.2f}s | Output Tokens: {token_count}")
                            
                        except Exception as e:
                            await renderer.update_message(msg_id, output + f"\n\n**Error**: {e}", thinking, [])
                            metrics_label.set_text(f"Error")
                        
                        # Add a small delay/cleanup if needed between models
                        await asyncio.sleep(1.0)
                    
                    state['processing'] = False
                    state['stopping'] = False
                    update_btn()

                user_prompt.on('keydown.enter.prevent.exact', run_batch)
                run_btn = ui.button('Run Batch', on_click=run_batch).props('color=primary icon=play_arrow').classes('w-full h-12 text-lg')

        # Results Area (Container for dynamically created tabs)
        ui.label('Results').classes('text-lg font-bold mt-4 mb-2')
        results_container = ui.column().classes('w-full')
