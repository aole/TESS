from nicegui import ui, app
from utils.ollama_client import client
from utils.config import config_manager
from utils.chat_renderer import ConversationRenderer
from services.stream_service import stream_service
from services.arena_service import arena_service
from services.batch_service import batch_service
import asyncio
import uuid

async def create_page():
    page_client = ui.context.client
    
    # helper for scrolling
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

    # --- State Management ---
    current_battle_id = app.storage.user.get('arena_battle_id')
    battle_state = None
    
    if current_battle_id:
        battle_state = arena_service.get_battle(current_battle_id)
        # If invalid (server restart?), clear it
        if not battle_state:
            current_battle_id = None
            app.storage.user['arena_battle_id'] = None
    
    # Models
    try:
        models_data = await client.list_models()
        model_options = [m['model'] for m in models_data]
    except Exception as e:
        ui.notify(f'Failed to load models: {e}', type='negative')
        model_options = []

    # -- Left Drawer (Configuration) --
    with ui.left_drawer(value=True).classes('bg-[#18181b] border-r border-white/10'):
        with ui.column().classes('w-full h-full p-4 no-wrap'):
            ui.label('Configuration').classes('text-lg font-bold text-gray-200 mb-4')
            
            ui.label('System Prompt').classes('text-sm font-medium text-gray-400 mb-1')
            default_sys = battle_state['system_prompt'] if battle_state else ''
            system_prompt = ui.textarea(placeholder='You are a helpful assistant...', value=default_sys).props('dense rows=4 filled flat').classes('w-full text-sm mb-6 bg-white/5 rounded-md')

            ui.label('Models').classes('text-sm font-bold text-gray-300 mb-2')
            
            default_m1 = battle_state['model1'] if battle_state else (model_options[0] if len(model_options) > 0 else None)
            default_m2 = battle_state['model2'] if battle_state else (model_options[1] if len(model_options) > 1 else default_m1)

            model1_select = ui.select(
                options=model_options,
                label='Model 1',
                value=default_m1
            ).props('dense options-dense').classes('w-full bg-black/20 px-2 rounded mb-4')

            model2_select = ui.select(
                options=model_options,
                label='Model 2',
                value=default_m2
            ).props('dense options-dense').classes('w-full bg-black/20 px-2 rounded')

    # -- Main Content --
    with ui.column().classes('w-full h-[calc(100vh-3rem)] pt-8 px-4 flex-nowrap'):
        
        state = {'processing': False, 'stopping': False}
        send_btn = None
        
        messages1 = battle_state['messages1'] if battle_state else []
        messages2 = battle_state['messages2'] if battle_state else []
        
        # User Prompt Section
        with ui.card().classes('w-full glass-panel px-3 py-2 mb-2 z-10'):
            default_prompt = ''
            user_input = ui.textarea(label='User Prompt', placeholder='Type a message for both models...', value=default_prompt).props('dense rows=4').classes('w-full')
            
            with ui.row().classes('w-full justify-between items-center'):
                send_btn = ui.button(icon='send').props('flat round color=primary dense')
                clear_btn = ui.button('Clear Chat', icon='delete_sweep').props('flat color=negative text-sm dense')

            def update_btn():
                 if not send_btn: return
                 is_busy = stream_service.any_active() or batch_service.any_active()
                 if state['processing'] or is_busy:
                     if state['stopping']:
                         send_btn.props('icon=hourglass_empty color=warning')
                     else:
                         send_btn.props('icon=stop color=negative')
                 else:
                     send_btn.props('icon=send color=primary')
            
            ui.timer(1.0, update_btn)

        # Chat Areas
        with ui.grid(columns=2).classes('w-full flex-grow min-h-0 gap-4 mb-4 z-0'):
            # Area 1
            chat1 = ui.column().classes('h-full w-full flex-nowrap overflow-y-auto p-4 gap-4 rounded-lg bg-black/20 border border-white/5').props('id=arena-scroll-1')
            with chat1:
                ui.label('Model 1 Output').classes('text-xs text-muted mb-1')
            
            # Area 2
            chat2 = ui.column().classes('h-full w-full flex-nowrap overflow-y-auto p-4 gap-4 rounded-lg bg-black/20 border border-white/5').props('id=arena-scroll-2')
            with chat2:
                ui.label('Model 2 Output').classes('text-xs text-muted mb-1')

        # Renderers
        renderer1 = ConversationRenderer(chat1, show_avatars=True)
        renderer2 = ConversationRenderer(chat2, show_avatars=True)

        # Render initial
        if messages1: renderer1.render_messages(messages1)
        if messages2: renderer2.render_messages(messages2)

        def clear_chat():
            nonlocal current_battle_id, messages1, messages2, battle_state
            if state['processing'] or stream_service.any_active() or batch_service.any_active():
                state['stopping'] = True
                stream_service.stop_all()
                batch_service.stop_all()
                if current_battle_id:
                    b = arena_service.get_battle(current_battle_id)
                    if b:
                        stream_service.stop_generation(b['stream_id_1'])
                        stream_service.stop_generation(b['stream_id_2'])
                update_btn()

            current_battle_id = None
            app.storage.user['arena_battle_id'] = None
            battle_state = None
            messages1 = []
            messages2 = []
            
            renderer1.clear()
            with chat1:
                ui.label('Model 1 Output').classes('text-xs text-muted mb-1')
                
            renderer2.clear()
            with chat2:
                ui.label('Model 2 Output').classes('text-xs text-muted mb-1')
                
            ui.notify('Chat cleared. Ready for a new session.', type='info')
        
        clear_btn.on('click', clear_chat)
        
        # --- Event Handlers ---

        async def on_stream_event_1(event_type, *args):
            with page_client:
                if event_type == 'update_message':
                    msg_id, content, thinking, tool_calls = args
                    if msg_id not in renderer1._msg_elements:
                        msg = next((m for m in messages1 if m.get('id') == msg_id), None)
                        if msg:
                            renderer1.render_message(msg)
                    
                    await renderer1.update_message(msg_id, content, thinking, tool_calls)
                    await scroll_to_bottom('arena-scroll-1', check_position=True)
                elif event_type == 'new_message':
                     msg = args[0]
                     if msg.get('id') not in renderer1._msg_elements:
                         renderer1.render_message(msg)
                     await scroll_to_bottom('arena-scroll-1')
                elif event_type == 'error':
                    ui.notify(f"Model 1 Error: {args[0]}", type='negative')

        async def on_stream_event_2(event_type, *args):
            with page_client:
                if event_type == 'update_message':
                    msg_id, content, thinking, tool_calls = args
                    if msg_id not in renderer2._msg_elements:
                        msg = next((m for m in messages2 if m.get('id') == msg_id), None)
                        if msg:
                            renderer2.render_message(msg)

                    await renderer2.update_message(msg_id, content, thinking, tool_calls)
                    await scroll_to_bottom('arena-scroll-2', check_position=True)
                elif event_type == 'new_message':
                     msg = args[0]
                     if msg.get('id') not in renderer2._msg_elements:
                         renderer2.render_message(msg)
                     await scroll_to_bottom('arena-scroll-2')
                elif event_type == 'error':
                    ui.notify(f"Model 2 Error: {args[0]}", type='negative')

        async def run_battle():
            nonlocal current_battle_id, messages1, messages2
            
            if state['processing'] or stream_service.any_active() or batch_service.any_active():
                state['stopping'] = True
                stream_service.stop_all()
                batch_service.stop_all()
                
                if current_battle_id:
                    b = arena_service.get_battle(current_battle_id)
                    if b:
                        stream_service.stop_generation(b['stream_id_1'])
                        stream_service.stop_generation(b['stream_id_2'])
                update_btn()
                return

            content = user_input.value
            model1 = model1_select.value
            model2 = model2_select.value
            
            if not content or not model1 or not model2:
                ui.notify('Please select both models and enter a prompt.', type='warning')
                return
            
            user_input.value = ''
            state['processing'] = True
            state['stopping'] = False
            update_btn()

            if not current_battle_id:
                current_battle_id = arena_service.start_battle(model1, model2, system_prompt.value)
                app.storage.user['arena_battle_id'] = current_battle_id
                b = arena_service.get_battle(current_battle_id)
                messages1 = b['messages1']
                messages2 = b['messages2']
            else:
                b = arena_service.get_battle(current_battle_id)
                b['model1'] = model1
                b['model2'] = model2
                b['system_prompt'] = system_prompt.value
            
            b = arena_service.get_battle(current_battle_id)
            sid1 = b['stream_id_1']
            sid2 = b['stream_id_2']

            user_msg = {'id': str(uuid.uuid4()), 'role': 'user', 'content': content}
            messages1.append(user_msg.copy())
            messages2.append(user_msg.copy())
            
            renderer1.render_message(user_msg)
            renderer2.render_message(user_msg)
            
            await scroll_to_bottom('arena-scroll-1')
            await scroll_to_bottom('arena-scroll-2')

            t1 = await stream_service.start_generation(
                stream_id=sid1,
                messages=messages1,
                model=model1,
                system_prompt=system_prompt.value,
                log_requests=config_manager.is_logging_enabled('arena'),
                listener=on_stream_event_1,
                keep_alive=0
            )

            t2 = await stream_service.start_generation(
                stream_id=sid2,
                messages=messages2,
                model=model2,
                system_prompt=system_prompt.value,
                log_requests=config_manager.is_logging_enabled('arena'),
                listener=on_stream_event_2,
                keep_alive=0
            )
            
            try:
                await asyncio.gather(t1, t2)
            except:
                pass
            
            state['processing'] = False
            state['stopping'] = False
            update_btn()

        user_input.on('keydown.enter.exact', lambda e: run_battle() if not e.args['shiftKey'] else None, args=['shiftKey'])
        send_btn.on('click', run_battle)
        
        # --- Re-attach (On Load) ---
        if current_battle_id:
            b = arena_service.get_battle(current_battle_id)
            if b:
                sid1 = b['stream_id_1']
                sid2 = b['stream_id_2']
                
                stream_service.register_listener(sid1, on_stream_event_1)
                stream_service.register_listener(sid2, on_stream_event_2)
                
                ui.context.client.on_disconnect(lambda: (
                    stream_service.unregister_listener(sid1),
                    stream_service.unregister_listener(sid2)
                ))
                
                if stream_service.is_streaming(sid1) or stream_service.is_streaming(sid2):
                     state['processing'] = True
                     update_btn()
                     
                     async def check_completion():
                         while stream_service.is_streaming(sid1) or stream_service.is_streaming(sid2):
                             await asyncio.sleep(0.5)
                         state['processing'] = False
                         update_btn()
                     
                     asyncio.create_task(check_completion())

