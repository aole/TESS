from nicegui import ui, app
from utils.llm_client import client
from utils.config import config_manager
from utils.chat_renderer import ConversationRenderer
from services.batch_service import batch_service
from services.stream_service import stream_service
from services.persona_service import persona_service
import asyncio
import uuid
import time

async def create_page():
    page_client = ui.context.client
    
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

    # -- Data Loading --
    try:
         models_data = await client.list_models()
         all_models = [m['model'] for m in models_data]
    except Exception as e:
         ui.notify(f"Error loading models: {e}", type='negative')
         all_models = []
    model_numbers = {model: index for index, model in enumerate(all_models, start=1)}

    # -- State --
    current_batch_id = app.storage.user.get('batch_id')
    batch_state = None
    if current_batch_id:
        batch_state = batch_service.get_batch(current_batch_id)
        if not batch_state:
            current_batch_id = None
            app.storage.user['batch_id'] = None

    model_toggles = {}
    # If recovering state, we might want to set toggles based on batch_state['models']? 
    # But user might want to run a new batch. 
    # Let's simple init toggles to unchecked or based on recovering if we are strictly in "view mode".
    # For now, standard init.
    
    run_btn = None 
    results_container = None 

    # -- Left Drawer (Configuration) --
    with ui.left_drawer(value=True).classes('bg-[#18181b] border-r border-white/10'):
        with ui.column().classes('w-full h-full p-4 no-wrap'):
            ui.label('Configuration').classes('text-lg font-bold text-gray-200 mb-4')

            # Persona picker
            ui.label('Persona').classes('text-sm font-medium text-gray-400 mb-1')

            def _build_persona_opts():
                opts = persona_service.get_all_persona_options()
                return {p['id']: p['name'] for p in opts}

            _default_persona = persona_service.get_default_persona()
            _initial_persona_id = app.storage.user.get(
                'selected_persona_id',
                _default_persona['id'],
            )
            _initial_persona = persona_service.get_persona(_initial_persona_id) or _default_persona

            def _on_persona_change(e):
                pid = e.value
                app.storage.user['selected_persona_id'] = pid
                persona = persona_service.get_persona(pid)
                if persona is not None:
                    system_prompt.value = persona['system_prompt']

            persona_select = ui.select(
                options=_build_persona_opts(),
                value=_initial_persona_id,
                on_change=_on_persona_change,
            ).props('dense options-dense outlined dark').classes('w-full text-sm mb-2')

            # Refresh persona options periodically (picks up newly created personas)
            def _refresh_persona_opts():
                persona_select.options = _build_persona_opts()

            ui.timer(3.0, _refresh_persona_opts)
            
            # System Prompt
            ui.label('System Prompt').classes('text-sm font-medium text-gray-400 mb-1')
            default_sys = batch_state['system_prompt'] if batch_state else _initial_persona['system_prompt']
            system_prompt = ui.textarea(placeholder='You are a helpful assistant...', value=default_sys).props('dense rows=4 filled flat').classes('w-full text-sm mb-6 bg-white/5 rounded-md')

            # Model Selection
            with ui.row().classes('w-full justify-between items-center mb-2'):
                ui.label('Models').classes('text-sm font-bold text-gray-300')
                with ui.row().classes('gap-1'):
                    def toggle_all(value):
                        for t in model_toggles.values():
                            t.value = value
                    
                    ui.button('All', on_click=lambda: toggle_all(True)).props('dense flat size=sm color=secondary')
                    ui.button('None', on_click=lambda: toggle_all(False)).props('dense flat size=sm text-color=grey')
            
            with ui.scroll_area().classes('flex-grow -mr-2 pr-2'):
                with ui.column().classes('gap-1'):
                    # Pre-select if recovering?
                    rec_models = set(batch_state['models']) if batch_state else set()
                    
                    for m in all_models:
                        is_checked = m in rec_models if batch_state else False
                        with ui.row().classes('w-full items-center gap-1 no-wrap m-0 p-0'):
                            ui.label(str(model_numbers[m])).classes('w-4 shrink-0 text-right text-[10px] leading-none font-mono text-teal-300')
                            t = ui.checkbox(m, value=is_checked).props('dense color=secondary size=sm').classes('min-w-0 text-sm text-gray-400')
                            model_toggles[m] = t

    # -- Main Content --
    with ui.column().classes('w-full h-full pt-8 px-4 max-w-7xl mx-auto'):
        
        state = {'stopping': False}

        # User Prompt Section
        with ui.card().classes('w-full glass-panel px-3 py-2 mb-2 z-10'):
            default_prompt = batch_state['user_prompt'] if batch_state else ''
            user_prompt = ui.textarea(label='User Prompt', placeholder='Tell me a joke...', value=default_prompt).props('dense rows=4').classes('w-full')
            
            with ui.row().classes('w-full justify-between items-center'):
                run_btn = ui.button(icon='send').props('flat round color=primary dense')
                clear_btn = ui.button('Clear Batch', icon='delete_sweep').props('flat color=negative text-sm dense')

            def update_btn():
                if not run_btn: return
                
                # Check Global or Local
                is_busy = stream_service.any_active() or batch_service.any_active()
                
                if is_busy:
                    if state['stopping']:
                        run_btn.props('icon=hourglass_empty color=warning')
                    else:
                        run_btn.props('icon=stop color=negative')
                else:
                    run_btn.props('icon=send color=primary')
                    state['stopping'] = False
            
            ui.timer(1.0, update_btn)

            async def run_batch():
                nonlocal current_batch_id, batch_state
                
                # Check if running
                # Check if Global Busy
                if stream_service.any_active() or batch_service.any_active():
                    state['stopping'] = True
                    batch_service.stop_all()
                    stream_service.stop_all()
                    update_btn()
                    return

                # Start New
                targets = [name for name, toggle in model_toggles.items() if toggle.value]
                if not targets:
                    ui.notify('Select at least one model', type='warning')
                    return
                if not user_prompt.value:
                    ui.notify('Enter a prompt', type='warning')
                    return
                
                state['stopping'] = False
                current_batch_id = batch_service.start_batch(user_prompt.value, system_prompt.value, targets)
                app.storage.user['batch_id'] = current_batch_id
                batch_state = batch_service.get_batch(current_batch_id)
                
                render_results_ui() # Re-render tabs
                update_btn()
                
                # Start poll for UI updates
                asyncio.create_task(poll_batch_updates())

            user_prompt.on('keydown.enter.exact', lambda e: run_batch() if not e.args['shiftKey'] else None, args=['shiftKey'])
            run_btn.on('click', run_batch)
            
            def clear_batch():
                nonlocal current_batch_id, batch_state
                if stream_service.any_active() or batch_service.any_active():
                    state['stopping'] = True
                    batch_service.stop_all()
                    stream_service.stop_all()
                    update_btn()

                current_batch_id = None
                app.storage.user['batch_id'] = None
                batch_state = None
                
                results_container.clear()
                model_renderers.clear()
                model_metrics.clear()
                model_scroll_ids.clear()
                
                ui.notify('Batch cleared. Ready for a new run.', type='info')
            
            clear_btn.on('click', clear_batch)

        # Results Area
        results_container = ui.column().classes('w-full flex-grow')
        
        # UI References for updates
        model_renderers = {}
        model_metrics = {}
        model_scroll_ids = {}
        
        def render_results_ui():
            results_container.clear()
            model_renderers.clear()
            model_metrics.clear()
            model_scroll_ids.clear()
            
            if not batch_state: return
            
            targets = batch_state['models']
            
            with results_container:
                tabs = ui.tabs().classes('w-full text-teal-400')
                panels = ui.tab_panels(tabs, value=targets[0]).classes('w-full rounded-b-lg bg-black/20 border border-white/5 min-h-[300px]')
                
                with tabs:
                    for index, model in enumerate(targets, start=1):
                        label = str(model_numbers.get(model, index))
                        ui.tab(model, label=label).tooltip(model)
                
                with panels:
                    for model in targets:
                        with ui.tab_panel(model).classes('h-[60vh] p-0'):
                            uid = f"batch-res-{model}-{uuid.uuid4()}" # Unique ID
                            model_scroll_ids[model] = uid
                            
                            with ui.column().classes('w-full h-full overflow-y-auto p-4 gap-4').props(f'id={uid}'):
                                # Metrics
                                with ui.row().classes('w-full items-center gap-4 mb-2 text-xs text-gray-400 font-mono border-b border-gray-700 pb-2'):
                                    model_metrics[model] = ui.label('Waiting...')
                                
                                # Renderer
                                r_container = ui.column().classes('w-full flex-grow')
                                
                                def make_delete_handler(m_name):
                                    def handle_delete(msg):
                                        if not batch_state: return
                                        m_state = batch_state['model_states'][m_name]
                                        m_messages = m_state['messages']
                                        indices = ConversationRenderer.get_turn_indices(m_messages, msg)
                                        if indices:
                                            m_messages[:] = [m for i, m in enumerate(m_messages) if i not in indices]
                                            model_renderers[m_name].render_messages(m_messages)
                                    return handle_delete

                                renderer = ConversationRenderer(r_container, on_delete=make_delete_handler(model))
                                model_renderers[model] = renderer
                                
                                # Initial render of messages
                                msgs = batch_state['model_states'][model]['messages']
                                renderer.render_messages(msgs)

        async def poll_batch_updates():
            # Capture the client context where this poller was started
            # page_client captured from outer scope
            while current_batch_id:
                if page_client._deleted:
                    break
                try:
                    with page_client:
                         pass # Just ensuring context is alive
                except:
                    break # Client disconnected
                
                b = batch_service.get_batch(current_batch_id)
                if not b: break
                
                # Update loop
                all_done = True
                
                with page_client:
                    for model in b['models']:
                        m_state = b['model_states'][model]
                        status = m_state['status']
                        
                        if status in ['generating', 'waiting']: 
                            all_done = False
                        
                        # Update Metrics
                        label = model_metrics.get(model)
                        if label:
                            if status == 'waiting': label.set_text('Waiting...')
                            elif status == 'generating': label.set_text(f"Generating... ({m_state['time']:.1f}s)")
                            elif status == 'done': label.set_text(f"Done in {m_state['time']:.2f}s")
                            elif status == 'cancelled': label.set_text('Cancelled')
                            elif status == 'error': label.set_text('Error')

                        # Update Content (Renderer)
                        renderer = model_renderers.get(model)
                        if renderer:
                            msgs = m_state['messages']
                            if msgs:
                                last_msg = msgs[-1]
                                if 'id' in last_msg:
                                    # We assume 'assistant' is last.
                                    # We assume 'assistant' is last.
                                    if last_msg['role'] == 'assistant':
                                        # Ensure message is rendered first
                                        if last_msg['id'] not in renderer._msg_elements:
                                             renderer.render_message(last_msg)

                                        await renderer.update_message(
                                            last_msg['id'], 
                                            last_msg.get('content',''), 
                                            last_msg.get('thinking',''), 
                                            last_msg.get('tool_calls', []),
                                            last_msg.get('stats')
                                        )
                                        # Auto-scroll
                                        # Ensure context for scroll js
                                        try:
                                            await scroll_to_bottom(model_scroll_ids[model], check_position=True)
                                        except:
                                            pass
                
                if all_done:
                    update_btn()
                    break
                
                if b['status'] == 'stopped':
                    update_btn()
                    break

                await asyncio.sleep(0.5)

        # Init (Recover)
        if current_batch_id:
            render_results_ui()
            update_btn()
            # If still running, attach poller
            if batch_state and batch_state['status'] == 'running':
                 asyncio.create_task(poll_batch_updates())


