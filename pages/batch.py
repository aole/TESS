from nicegui import ui, app
from utils.llm_client import client
from utils.config import config_manager
from utils.chat_renderer import ConversationRenderer
from services.batch_service import batch_service
from services.stream_service import stream_service
from services.persona_service import persona_service
import asyncio
import json
import uuid
import time

DEFAULT_JUDGE_SYSTEM_PROMPT = """You are StoryJudge, an impartial evaluator of fictional stories written by other language models.

Your job is to evaluate the submitted story using the provided rubric. You must judge only the story text given to you, not the author, model, prompt, or your personal taste.

Be fair, consistent, and strict. Do not rewrite the story unless explicitly asked. Do not reward length by itself. Do not penalize unusual style choices if they are intentional and effective.

Evaluate the story across the required categories. For each category:
- Give a numeric score.
- Give a short reason for the score.
- Mention concrete evidence from the story.
- Identify the main weakness if applicable.

Use the full scoring range. Do not cluster everything around the middle. Excellent stories should score high, weak stories should score low.

If the story is incomplete, incoherent, plagiarized-looking, mostly non-story content, or does not follow the effective prompt, reflect that in the scores.

Return your answer in valid JSON only. Do not include markdown, commentary, or extra text outside the JSON."""

DEFAULT_JUDGE_PROMPT_TEMPLATE = '''Evaluate the following story.

Effective prompt:
{{EFFECTIVE_PROMPT}}

Story to evaluate:
"""
{{STORY_TEXT}}
"""

Use this scoring rubric:

1. Plot and Structure - 0 to 10
Evaluate whether the story has a clear beginning, middle, and end; meaningful progression; conflict; escalation; and resolution.

2. Character Quality - 0 to 10
Evaluate whether the characters feel distinct, believable, motivated, and emotionally engaging.

3. Originality - 0 to 10
Evaluate whether the story avoids cliches, offers fresh ideas, and has a memorable premise or execution.

4. Worldbuilding and Setting - 0 to 10
Evaluate whether the setting is clear, immersive, and relevant to the story.

5. Prose and Style - 0 to 10
Evaluate sentence quality, readability, tone, imagery, pacing, and command of language.

6. Dialogue - 0 to 10
Evaluate whether dialogue sounds natural, reveals character, advances the story, and avoids exposition dumping.

7. Emotional Impact - 0 to 10
Evaluate whether the story creates tension, humor, sadness, wonder, fear, or another intended emotional response.

8. Theme and Meaning - 0 to 10
Evaluate whether the story has depth, thematic coherence, or something meaningful beneath the surface.

9. Prompt Adherence - 0 to 10
Evaluate how well the story follows the effective prompt.

10. Overall Quality - 0 to 10
Evaluate the story as a complete reading experience.

Scoring guide:
0 = Missing or unusable
1-2 = Very poor
3-4 = Weak
5-6 = Adequate
7-8 = Strong
9 = Excellent
10 = Exceptional

Return valid JSON in this exact structure:

{
  "scores": {
    "plot_and_structure": {
      "score": 0,
      "reason": ""
    },
    "character_quality": {
      "score": 0,
      "reason": ""
    },
    "originality": {
      "score": 0,
      "reason": ""
    },
    "worldbuilding_and_setting": {
      "score": 0,
      "reason": ""
    },
    "prose_and_style": {
      "score": 0,
      "reason": ""
    },
    "dialogue": {
      "score": 0,
      "reason": ""
    },
    "emotional_impact": {
      "score": 0,
      "reason": ""
    },
    "theme_and_meaning": {
      "score": 0,
      "reason": ""
    },
    "prompt_adherence": {
      "score": 0,
      "reason": ""
    },
    "overall_quality": {
      "score": 0,
      "reason": ""
    }
  },
  "weighted_total": 0,
  "grade": "",
  "summary": "",
  "top_strengths": [],
  "top_weaknesses": [],
  "suggested_improvements": [],
  "red_flags": []
}

Calculate weighted_total using this weighting:
- Plot and Structure: 15%
- Character Quality: 12%
- Originality: 10%
- Worldbuilding and Setting: 8%
- Prose and Style: 12%
- Dialogue: 8%
- Emotional Impact: 10%
- Theme and Meaning: 8%
- Prompt Adherence: 10%
- Overall Quality: 7%

Use this grade scale:
9.0 to 10 = "A"
8.0 to 8.9 = "B"
7.0 to 7.9 = "C"
6.0 to 6.9 = "D"
Below 6.0 = "F"

Rules:
- Scores must be numbers from 0 to 10.
- Reasons must be specific, not generic.
- Do not give a high score if the reason describes serious flaws.
- If the story violates the effective prompt, reduce prompt_adherence.
- If the story is very short, judge whether it still works as flash fiction rather than automatically penalizing it.
- If the story is incomplete, mention it in red_flags.
- Return JSON only.'''

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
        if raw_content.startswith('```'):
            raw_content = raw_content.removeprefix('```json').removeprefix('```').strip()
            raw_content = raw_content.removesuffix('```').strip()
        try:
            data = json.loads(raw_content)
        except Exception:
            start = raw_content.find('{')
            if start == -1:
                return content
            try:
                data, _ = json.JSONDecoder().raw_decode(raw_content[start:])
            except Exception:
                return content

        def clean(value):
            return str(value if value is not None else '').replace('|', '\\|').strip()

        lines = [
            '## Judge Evaluation',
            '',
            f"**Grade:** {clean(data.get('grade'))}",
            f"**Weighted total:** {clean(data.get('weighted_total'))}",
        ]

        summary = data.get('summary')
        if summary:
            lines.extend(['', f"**Summary:** {clean(summary)}"])

        scores = data.get('scores', {})
        if scores:
            lines.extend([
                '',
                '| Category | Score | Reason |',
                '| --- | ---: | --- |',
            ])
            for key, value in scores.items():
                category = key.replace('_', ' ').title()
                if isinstance(value, dict):
                    score = value.get('score', '')
                    reason = value.get('reason', '')
                else:
                    score = ''
                    reason = value
                lines.append(f"| {clean(category)} | {clean(score)} | {clean(reason)} |")

        for key, title in [
            ('top_strengths', 'Top Strengths'),
            ('top_weaknesses', 'Top Weaknesses'),
            ('suggested_improvements', 'Suggested Improvements'),
            ('red_flags', 'Red Flags'),
        ]:
            values = data.get(key) or []
            if values:
                lines.extend(['', f"**{title}:**"])
                lines.extend([f"- {clean(item)}" for item in values])

        return '\n'.join(lines)

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
                    log_requests=config_manager.is_logging_enabled('batch'),
                    keep_alive=0 if index == len(judge_targets) - 1 else '5m',
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
    saved_judge_template = app.storage.user.get('batch_judge_prompt_template', DEFAULT_JUDGE_PROMPT_TEMPLATE)
    if '{{ORIGINAL_PROMPT}}' in saved_judge_template:
        saved_judge_template = DEFAULT_JUDGE_PROMPT_TEMPLATE

    with ui.right_drawer(value=True).classes('bg-[#18181b] border-l border-white/10'):
        with ui.column().classes('w-full h-full p-4 no-wrap'):
            ui.label('Judge').classes('text-lg font-bold text-gray-200 mb-4')
            with ui.scroll_area().classes('w-full flex-grow -mr-2 pr-2'):
                ui.label('Judge Model').classes('text-sm font-medium text-gray-400 mb-1')
                judge_model = ui.select(
                    options=all_models,
                    value=judge_model_default,
                ).props('dense options-dense outlined dark').classes('w-full text-sm mb-4')

                ui.label('Judge LLM System Prompt').classes('text-sm font-medium text-gray-400 mb-1')
                judge_system_prompt = ui.textarea(
                    value=app.storage.user.get('batch_judge_system_prompt', DEFAULT_JUDGE_SYSTEM_PROMPT),
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


