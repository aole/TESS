from nicegui import ui
from utils.ollama_client import client
import asyncio

async def create_page():
    # Layout
    with ui.column().classes('w-full h-full pt-14 px-4 max-w-7xl mx-auto'):
        ui.label('Batch Processing').classes('text-xl font-bold mb-2 bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-cyan-400')
        
        # Data Loading
        try:
             models_data = await client.list_models()
             all_models = [m['model'] for m in models_data]
        except Exception as e:
             ui.notify(f"Error loading models: {e}", type='negative')
             all_models = []

        # Selection & Prompts
        with ui.row().classes('w-full gap-4 items-start'):
            # Model Selection
            with ui.card().classes('w-1/3 glass-panel p-4'):
                ui.label('Select Models').classes('text-lg font-bold mb-4')
                
                # Checkbox for each model
                selected_models = []
                # Use a container to hold toggles
                model_toggles = {}
                
                with ui.scroll_area().classes('h-64 pr-4'):
                    for m in all_models:
                        t = ui.checkbox(m).props('dense color=secondary')
                        model_toggles[m] = t

            # Prompts Area
            with ui.column().classes('w-2/3 gap-2'):
                system_prompt = ui.textarea(label='System Prompt', placeholder='You are...').props('dense rows=1').classes('w-full glass-panel px-4 rounded')
                user_prompt = ui.textarea(label='User Prompt', placeholder='Tell me a joke...').props('dense rows=2').classes('w-full glass-panel px-4 rounded')
                
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
                    results_grid.clear()
                    
                    # Prepare messages
                    msgs = []
                    if system_prompt.value:
                        msgs.append({'role': 'system', 'content': system_prompt.value})
                    msgs.append({'role': 'user', 'content': user_prompt.value})

                    # Create cards for each target
                    result_cards = {}
                    with results_grid:
                        for model in targets:
                            with ui.card().classes('glass-panel p-4 flex flex-col gap-2 min-h-[200px]'):
                                ui.label(model).classes('text-lg font-bold text-indigo-300')
                                content_area = ui.markdown('Waiting...').classes('text-sm text-gray-300')
                                result_cards[model] = content_area
                    
                    # Sequential Execution
                    for model in targets:
                        if state['stopping']:
                            card = result_cards[model]
                            card.set_content('**Batch processing stopped**')
                            break

                        card = result_cards[model]
                        card.set_content('**Generating...**')
                        
                        output = ""
                        try:
                            stream = await client.chat(model=model, messages=msgs, stream=True)
                            async for chunk in stream:
                                if state['stopping']:
                                    card.set_content(output + '\n\n**Stopped**')
                                    break
                                part = chunk.get('message', {}).get('content', '')
                                output += part
                                card.set_content(output)
                                # yield to UI implicit
                        except Exception as e:
                            card.set_content(f'**Error**: {e}')
                        
                        # Add a small delay/cleanup if needed between models
                        await asyncio.sleep(0.5)
                    
                    state['processing'] = False
                    state['stopping'] = False
                    update_btn()

                run_btn = ui.button('Run Batch', on_click=run_batch).props('color=primary icon=play_arrow').classes('w-full h-12 text-lg')

        # Results Area
        ui.label('Results').classes('text-lg font-bold mt-4 mb-2')
        results_grid = ui.grid(columns=3).classes('w-full gap-2 pb-4')
