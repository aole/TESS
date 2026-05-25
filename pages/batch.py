from nicegui import ui, app
from utils.llm_client import client
from utils.config import config_manager
from utils.chat_renderer import ConversationRenderer
from services.batch_service import batch_service
from services.stream_service import stream_service
from services.persona_service import persona_service
import asyncio
import json
from pathlib import Path
import tomllib
import uuid
import time

JUDGE_PRESETS_DIR = Path('data/judges')

def load_judge_presets():
    presets = {}
    for path in sorted(JUDGE_PRESETS_DIR.glob('*.toml')):
        try:
            data = tomllib.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"Error loading judge preset {path}: {e}")
            continue

        preset_id = data.get('id') or path.stem
        presets[preset_id] = {
            'name': data.get('name') or preset_id.replace('_', ' ').title(),
            'system_prompt': data.get('system_prompt', ''),
            'prompt_template': data.get('prompt_template', ''),
        }
    return presets

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
    judge_state = {'running': False, 'stop_requested': False}

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

    def _judge_prompt_from_template(template: str, effective_prompt: str, story_text: str) -> str:
        replacements = {
            '{{EFFECTIVE_PROMPT}}': effective_prompt or '',
            '{{STORY_TEXT}}': story_text or '',
        }
        for placeholder, value in replacements.items():
            template = template.replace(placeholder, value)
        return template

    def _get_last_user_text(messages):
        for msg in reversed(messages):
            if msg.get('role') == 'user' and not msg.get('judge_evaluation'):
                return msg.get('content', '')
        return ''

    def _get_story_text(messages):
        for msg in reversed(messages):
            if msg.get('role') == 'assistant' and not msg.get('judge_evaluation'):
                return msg.get('content', '')
        return ''

    def _format_judge_output(content: str) -> str:
        raw_content = content.strip()

        def clean(value):
            return str(value if value is not None else '').replace('|', '\\|').strip()

        def title_for_key(key: str) -> str:
            return str(key).replace('_', ' ').title()

        def scalar_text(value) -> str:
            if isinstance(value, bool):
                return 'true' if value else 'false'
            if value is None:
                return ''
            return clean(value)

        def is_scalar(value) -> bool:
            return not isinstance(value, (dict, list))

        def append_markdown(lines, value, level=2, title=None):
            if isinstance(value, dict):
                if title:
                    lines.extend(['', f"{'#' * min(level, 6)} {clean(title)}"])

                scalar_items = [(key, item) for key, item in value.items() if is_scalar(item)]
                complex_items = [(key, item) for key, item in value.items() if not is_scalar(item)]

                if scalar_items:
                    for key, item in scalar_items:
                        lines.append(f"**{clean(title_for_key(key))}:** {scalar_text(item)}")

                if complex_items and all(isinstance(item, dict) for _, item in complex_items):
                    child_keys = []
                    for _, item in complex_items:
                        for child_key, child_value in item.items():
                            if is_scalar(child_value) and child_key not in child_keys:
                                child_keys.append(child_key)

                    if child_keys:
                        lines.extend(['', '| Item | ' + ' | '.join(clean(title_for_key(key)) for key in child_keys) + ' |'])
                        lines.append('| --- | ' + ' | '.join('---' for _ in child_keys) + ' |')
                        for key, item in complex_items:
                            cells = [clean(title_for_key(key))]
                            cells.extend(scalar_text(item.get(child_key, '')) for child_key in child_keys)
                            lines.append('| ' + ' | '.join(cells) + ' |')

                        for key, item in complex_items:
                            nested = {child_key: child_value for child_key, child_value in item.items() if not is_scalar(child_value)}
                            if nested:
                                append_markdown(lines, nested, level + 1, title_for_key(key))
                    else:
                        for key, item in complex_items:
                            append_markdown(lines, item, level + 1, title_for_key(key))
                else:
                    for key, item in complex_items:
                        append_markdown(lines, item, level + 1, title_for_key(key))
            elif isinstance(value, list):
                if title:
                    lines.extend(['', f"{'#' * min(level, 6)} {clean(title)}"])
                if all(is_scalar(item) for item in value):
                    lines.extend(f"- {scalar_text(item)}" for item in value)
                else:
                    for index, item in enumerate(value, start=1):
                        append_markdown(lines, item, level + 1, f"Item {index}")
            elif title:
                lines.append(f"**{clean(title)}:** {scalar_text(value)}")

        def format_json_data(data: dict) -> str:
            lines = ['## Judge Evaluation']
            append_markdown(lines, data)
            return '\n'.join(lines)

        def strip_fence(value: str) -> str:
            value = value.strip()
            if not value.startswith('```'):
                return value
            first_newline = value.find('\n')
            if first_newline != -1:
                value = value[first_newline + 1:]
            if value.rstrip().endswith('```'):
                value = value.rstrip()[:-3]
            return value.strip()

        def extract_json_object(value: str) -> str:
            start = value.find('{')
            if start == -1:
                return ''

            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(value)):
                char = value[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == '\\':
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue

                if char == '"':
                    in_string = True
                elif char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        return value[start:index + 1]
            return value[start:]

        def escape_control_chars_in_strings(value: str) -> str:
            result = []
            in_string = False
            escaped = False
            for char in value:
                if in_string:
                    if escaped:
                        result.append(char)
                        escaped = False
                    elif char == '\\':
                        result.append(char)
                        escaped = True
                    elif char == '"':
                        result.append(char)
                        in_string = False
                    elif char == '\n':
                        result.append('\\n')
                    elif char == '\r':
                        result.append('\\r')
                    elif char == '\t':
                        result.append('\\t')
                    else:
                        result.append(char)
                else:
                    result.append(char)
                    if char == '"':
                        in_string = True
            return ''.join(result)

        parse_candidates = [
            raw_content,
            strip_fence(raw_content),
            extract_json_object(strip_fence(raw_content)),
            extract_json_object(raw_content),
        ]

        data = None
        for candidate in parse_candidates:
            if not candidate:
                continue
            for parse_candidate in [candidate, escape_control_chars_in_strings(candidate)]:
                try:
                    data = json.loads(parse_candidate)
                    break
                except Exception:
                    try:
                        data, _ = json.JSONDecoder().raw_decode(parse_candidate)
                        break
                    except Exception:
                        pass
            if data is not None:
                break

        if not isinstance(data, dict):
            return content

        return format_json_data(data)

    def _format_stored_judge_messages(messages):
        for msg in messages:
            if msg.get('role') != 'assistant' or not msg.get('judge_evaluation'):
                continue
            raw_content = msg.get('raw_judge_json') or msg.get('content', '')
            formatted_content = _format_judge_output(raw_content)
            if formatted_content != raw_content:
                msg['raw_judge_json'] = raw_content
                msg['content'] = formatted_content

    async def run_judge():
        nonlocal batch_state

        if judge_state['running']:
            judge_state['stop_requested'] = True
            judge_btn.props('icon=hourglass_empty color=warning')
            judge_btn.set_text('Stopping')
            judge_status.set_text('Stopping judge...')
            update_btn()
            return
        if batch_service.any_active() or stream_service.any_active():
            state['stopping'] = True
            batch_service.stop_all()
            stream_service.stop_all()
            judge_btn.props('icon=hourglass_empty color=warning')
            judge_btn.set_text('Stopping')
            judge_status.set_text('Stopping batch...')
            update_btn()
            return
        if not batch_state:
            ui.notify('Run or recover a batch before judging.', type='warning')
            return
        if not judge_model.value:
            ui.notify('Select a judge model.', type='warning')
            return

        app.storage.user['batch_judge_model'] = judge_model.value
        app.storage.user['batch_judge_preset'] = judge_preset.value
        app.storage.user['batch_judge_system_prompt'] = judge_system_prompt.value
        app.storage.user['batch_judge_prompt_template'] = judge_prompt_template.value

        judge_state['running'] = True
        judge_state['stop_requested'] = False
        judge_btn.props('icon=stop color=negative')
        judge_btn.set_text('Stop')
        judge_status.set_text('Judging...')
        update_btn()

        judged_count = 0
        try:
            judge_targets = []
            for model in batch_state['models']:
                m_state = batch_state['model_states'][model]
                if m_state.get('status') != 'done':
                    continue

                story_text = _get_story_text(m_state['messages'])
                if not story_text.strip():
                    continue

                judge_targets.append((model, m_state, story_text))

            for index, (model, m_state, story_text) in enumerate(judge_targets):
                if judge_state['stop_requested']:
                    break

                judge_status.set_text(f'Judging {model_numbers.get(model, model)}...')
                effective_prompt = '\n\n'.join(
                    part for part in [
                        batch_state.get('system_prompt', ''),
                        _get_last_user_text(m_state['messages']),
                    ]
                    if part
                )
                prompt = _judge_prompt_from_template(
                    judge_prompt_template.value,
                    effective_prompt,
                    story_text,
                )
                user_msg = {
                    'id': str(uuid.uuid4()),
                    'role': 'user',
                    'content': 'Judge evaluation requested.',
                    'judge_evaluation': True,
                }
                assistant_msg = {
                    'id': str(uuid.uuid4()),
                    'role': 'assistant',
                    'model': f'Judge: {judge_model.value}',
                    'content': '',
                    'thinking': '',
                    'raw_judge_json': '',
                    'judge_evaluation': True,
                }
                m_state['messages'].extend([user_msg, assistant_msg])
                render_results_ui()

                stream = await client.chat(
                    judge_model.value,
                    [
                        {'role': 'system', 'content': judge_system_prompt.value},
                        {'role': 'user', 'content': prompt},
                    ],
                    stream=True,
                    options={
                        'temperature': 0.1,
                        'top_p': 1,
                        'repeat_penalty': 1.0,
                    },
                    log_requests=config_manager.is_logging_enabled('batch'),
                    keep_alive=0 if index == len(judge_targets) - 1 else '5m',
                    format='json',
                )
                content = ''
                thinking = ''
                stats = None
                async for chunk in stream:
                    if judge_state['stop_requested']:
                        break

                    msg_chunk = chunk.get('message', {})
                    content += msg_chunk.get('content', '') or ''
                    thinking += msg_chunk.get('thinking', '') or ''
                    if chunk.get('done'):
                        stats = chunk

                    assistant_msg['content'] = content
                    assistant_msg['thinking'] = thinking
                    renderer = model_renderers.get(model)
                    if renderer:
                        await renderer.update_message(
                            assistant_msg['id'],
                            content or '...',
                            thinking,
                            [],
                            stats,
                        )

                if not content:
                    content = '_Stopped by user_' if judge_state['stop_requested'] else 'Error: judge returned an empty response.'
                display_content = _format_judge_output(content)

                assistant_msg['content'] = display_content
                assistant_msg['thinking'] = thinking
                assistant_msg['raw_judge_json'] = content
                renderer = model_renderers.get(model)
                if renderer:
                    await renderer.update_message(
                        assistant_msg['id'],
                        display_content,
                        thinking,
                        [],
                        stats,
                    )
                if not judge_state['stop_requested']:
                    judged_count += 1

            if judge_state['stop_requested']:
                judge_status.set_text(f'Stopped after {judged_count} outputs.')
                ui.notify('Judge stopped.', type='info')
            elif judged_count:
                judge_status.set_text(f'Judged {judged_count} outputs.')
                ui.notify(f'Judged {judged_count} batch outputs.', type='positive')
            else:
                judge_status.set_text('No completed outputs to judge.')
                ui.notify('No completed batch outputs to judge.', type='warning')
        except Exception as e:
            judge_status.set_text('Judge failed.')
            ui.notify(f'Judge failed: {e}', type='negative')
        finally:
            judge_state['running'] = False
            judge_state['stop_requested'] = False
            judge_btn.props('icon=gavel color=secondary')
            judge_btn.set_text('Judge')
            update_btn()

    judge_model_default = app.storage.user.get('batch_judge_model')
    if judge_model_default not in all_models:
        judge_model_default = all_models[0] if all_models else None

    judge_presets = load_judge_presets()
    judge_options = {preset_id: preset['name'] for preset_id, preset in judge_presets.items()}
    judge_preset_default = app.storage.user.get('batch_judge_preset', 'story_judge')
    if judge_preset_default not in judge_presets:
        judge_preset_default = next(iter(judge_presets), None)
    selected_judge_preset = judge_presets.get(judge_preset_default, {})

    saved_judge_system_prompt = selected_judge_preset.get(
        'system_prompt',
        app.storage.user.get('batch_judge_system_prompt', ''),
    )
    saved_judge_template = selected_judge_preset.get(
        'prompt_template',
        app.storage.user.get('batch_judge_prompt_template', ''),
    )
    if '{{ORIGINAL_PROMPT}}' in saved_judge_template:
        saved_judge_template = selected_judge_preset.get('prompt_template', '')

    def on_judge_preset_change(e):
        preset = judge_presets.get(e.value)
        if not preset:
            return
        judge_system_prompt.value = preset['system_prompt']
        judge_prompt_template.value = preset['prompt_template']
        app.storage.user['batch_judge_preset'] = e.value
        app.storage.user['batch_judge_system_prompt'] = preset['system_prompt']
        app.storage.user['batch_judge_prompt_template'] = preset['prompt_template']

    with ui.right_drawer(value=True).classes('bg-[#18181b] border-l border-white/10'):
        with ui.column().classes('w-full h-full p-4 no-wrap'):
            ui.label('Judge').classes('text-lg font-bold text-gray-200 mb-4')
            with ui.scroll_area().classes('w-full flex-grow -mr-2 pr-2'):
                ui.label('Judge Model').classes('text-sm font-medium text-gray-400 mb-1')
                judge_model = ui.select(
                    options=all_models,
                    value=judge_model_default,
                ).props('dense options-dense outlined dark').classes('w-full text-sm mb-4')

                ui.label('Judge').classes('text-sm font-medium text-gray-400 mb-1')
                judge_preset = ui.select(
                    options=judge_options,
                    value=judge_preset_default,
                    on_change=on_judge_preset_change,
                ).props('dense options-dense outlined dark').classes('w-full text-sm mb-4')

                ui.label('Judge LLM System Prompt').classes('text-sm font-medium text-gray-400 mb-1')
                judge_system_prompt = ui.textarea(
                    value=saved_judge_system_prompt,
                ).props('dense rows=8 filled flat').classes('w-full text-sm mb-4 bg-white/5 rounded-md')

                ui.label('Judge Prompt Template').classes('text-sm font-medium text-gray-400 mb-1')
                judge_prompt_template = ui.textarea(
                    value=saved_judge_template,
                ).props('dense rows=12 filled flat').classes('w-full text-sm mb-4 bg-white/5 rounded-md')

            with ui.row().classes('w-full items-center justify-between gap-2'):
                judge_btn = ui.button('Judge', icon='gavel', on_click=run_judge).props('color=secondary dense')
                judge_status = ui.label('').classes('text-xs text-gray-500')

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
                is_batch_busy = stream_service.any_active() or batch_service.any_active()
                is_busy = is_batch_busy or judge_state['running']
                
                if is_busy:
                    if state['stopping']:
                        run_btn.props('icon=hourglass_empty color=warning')
                    else:
                        run_btn.props('icon=stop color=negative')
                else:
                    run_btn.props('icon=send color=primary')
                    state['stopping'] = False

                if judge_state['running']:
                    if judge_state['stop_requested']:
                        judge_btn.props('icon=hourglass_empty color=warning')
                        judge_btn.set_text('Stopping')
                    else:
                        judge_btn.props('icon=stop color=negative')
                        judge_btn.set_text('Stop')
                elif is_batch_busy:
                    if state['stopping']:
                        judge_btn.props('icon=hourglass_empty color=warning')
                        judge_btn.set_text('Stopping')
                    else:
                        judge_btn.props('icon=stop color=negative')
                        judge_btn.set_text('Stop')
                else:
                    judge_btn.props('icon=gavel color=secondary')
                    judge_btn.set_text('Judge')
            
            ui.timer(1.0, update_btn)

            async def run_batch():
                nonlocal current_batch_id, batch_state
                
                # Check if running
                # Check if Global Busy
                if stream_service.any_active() or batch_service.any_active() or judge_state['running']:
                    state['stopping'] = True
                    if judge_state['running']:
                        judge_state['stop_requested'] = True
                        judge_btn.props('icon=hourglass_empty color=warning')
                        judge_btn.set_text('Stopping')
                        judge_status.set_text('Stopping judge...')
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
                if stream_service.any_active() or batch_service.any_active() or judge_state['running']:
                    state['stopping'] = True
                    if judge_state['running']:
                        judge_state['stop_requested'] = True
                        judge_btn.props('icon=hourglass_empty color=warning')
                        judge_btn.set_text('Stopping')
                        judge_status.set_text('Stopping judge...')
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
                                _format_stored_judge_messages(msgs)
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


