from nicegui import ui
from utils.ollama_client import client
from utils.config import config_manager
import asyncio
import time

async def create_page():
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
                
                # Import here if not top-level, or assume standard lib is available. 
                # Better to add import at top, but for now inside content works if globally imported.
                
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
                        panels = ui.tab_panels(tabs, value=targets[0]).classes('w-full rounded-b-lg glass-panel min-h-[300px]')
                        
                        # Create tab header and panels
                        model_tabs = {}
                        model_panels = {}
                        model_content = {}
                        model_metrics = {}
                        
                        with tabs:
                            for model in targets:
                                t = ui.tab(model)
                                model_tabs[model] = t
                        
                        with panels:
                            for model in targets:
                                with ui.tab_panel(model):
                                    # Metrics Row
                                    with ui.row().classes('w-full items-center gap-4 mb-2 text-xs text-gray-400 font-mono border-b border-gray-700 pb-2'):
                                        model_metrics[model] = ui.label('Waiting...')
                                    
                                    # Content
                                    model_content[model] = ui.markdown('').classes('w-full')

                    # Sequential Execution
                    for model in targets:
                        if state['stopping']:
                            model_content[model].content = '**Batch processing stopped**'
                            break
                        
                        # Switch tab to current model
                        tabs.set_value(model)
                        
                        # Thinking visuals?
                        content_area = model_content[model]
                        metrics_label = model_metrics[model]
                        
                        metrics_label.set_text('Generating...')
                        
                        output = ""
                        thinking = ""
                        token_count = 0
                        t0 = time.time()
                        
                        try:
                            stream = await client.chat(model=model, messages=msgs, stream=True, log_requests=config_manager.is_logging_enabled('batch'))
                            async for chunk in stream:
                                if state['stopping']:
                                    content_area.content += '\n\n**Stopped**'
                                    await stream.aclose()
                                    break
                                
                                msg = chunk.get('message', {})
                                val = msg.get('content', '')
                                thk = msg.get('thinking', '')
                                
                                # Update Stats if available in chunk
                                if 'eval_count' in chunk:
                                    token_count = chunk['eval_count']
                                
                                if thk:
                                    thinking += thk
                                
                                output += val
                                
                                # Construct markdown
                                md_text = ""
                                if thinking:
                                    md_text += f"<details open><summary>Thinking process</summary>\n\n{thinking}\n\n</details>\n\n***\n***\n\n"
                                md_text += output
                                
                                content_area.content = md_text
                                # yield to UI implicit
                            
                            duration = time.time() - t0
                            # Final metrics update
                            metrics_label.set_text(f"Time: {duration:.2f}s | Output Tokens: {token_count}")
                            
                        except Exception as e:
                            content_area.content = f'**Error**: {e}'
                            metrics_label.set_text(f"Error")
                        
                        # Add a small delay/cleanup if needed between models
                        await asyncio.sleep(0.5)
                    
                    state['processing'] = False
                    state['stopping'] = False
                    update_btn()

                user_prompt.on('keydown.enter.prevent.exact', run_batch)
                run_btn = ui.button('Run Batch', on_click=run_batch).props('color=primary icon=play_arrow').classes('w-full h-12 text-lg')

        # Results Area (Container for dynamically created tabs)
        ui.label('Results').classes('text-lg font-bold mt-4 mb-2')
        results_container = ui.column().classes('w-full')


