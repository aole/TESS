import os
import asyncio
from nicegui import ui, run, app
from services.visual_service import generate_image_task


_VISUAL_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
_VISUAL_DIR  = 'data/visual'


def create_page():
    if 'visual_positive_prompt' not in app.storage.user:
        app.storage.user['visual_positive_prompt'] = (
            "masterpiece, best quality, score_7, safe, abandoned cathedral, nature reclaiming architecture, "
            "vines and flowers, shafts of sunlight, dust particles, tranquil atmosphere, Studio Ghibli inspired"
        )
    if 'visual_negative_prompt' not in app.storage.user:
        app.storage.user['visual_negative_prompt'] = (
            "worst quality, low quality, score_1, score_2, score_3, artist name, sepia"
        )
    if 'visual_image_size' not in app.storage.user:
        app.storage.user['visual_image_size'] = '1024x1024'
    if 'visual_inference_steps' not in app.storage.user:
        app.storage.user['visual_inference_steps'] = 30

    # ── Main two-column layout ───────────────────────────────────────────────
    with ui.row().classes('w-full max-w-screen-2xl mx-auto gap-6 p-4 flex-nowrap items-start'):

        # Left column – image area (70%)
        with ui.column().classes(
            'rounded-lg border border-white/10 overflow-hidden bg-black/20 '
            'items-center justify-center relative'
        ).style('flex: 7; min-height: 768px;') as image_container:
            last_image = app.storage.user.get('visual_last_image')
            if last_image and os.path.exists(last_image):
                ui.image(f'/{last_image}').classes('w-full h-full object-contain rounded-lg shadow-xl')
            else:
                ui.icon('image', size='64px').classes('text-white/10 mb-4')
                ui.label('Generated image will appear here').classes('text-white/30 text-lg')

        # Right column – settings (30%)
        with ui.column().classes('gap-6').style('flex: 3;'):
            prompt = ui.textarea(
                'Positive Prompt', placeholder='masterpiece, best quality... (Use /// to separate multiple prompts)'
            ).classes('w-full text-lg').props('outlined rows="10"').bind_value(
                app.storage.user, 'visual_positive_prompt'
            )

            negative_prompt = ui.textarea(
                'Negative Prompt', placeholder='worst quality, low quality, …'
            ).classes('w-full').props('outlined rows="4"').bind_value(
                app.storage.user, 'visual_negative_prompt'
            )

            with ui.column().classes('w-full gap-1'):
                ui.label('Image Size').classes('text-sm text-gray-400')
                image_size = ui.select(
                    options={
                        '1024x1024': '1024 × 1024 (1:1)',
                        '896x1152':  '896 × 1152 (3:4)',
                        '1152x896':  '1152 × 896 (4:3)',
                    }
                ).classes('w-full').bind_value(app.storage.user, 'visual_image_size')

            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('Inference Steps').classes('text-sm text-gray-400')
                    steps_label = ui.label(
                        str(app.storage.user['visual_inference_steps'])
                    ).classes('text-sm text-gray-300 font-mono')
                steps = ui.slider(
                    min=1, max=50,
                    on_change=lambda e: steps_label.set_text(str(int(e.value)))
                ).classes('w-full').bind_value(app.storage.user, 'visual_inference_steps')

            # Generate / Clear
            with ui.row().classes('w-full gap-4 mt-2 flex-nowrap'):
                generate_btn = ui.button('Generate', icon='brush').classes(
                    'flex-grow h-16 text-xl '
                    'bg-gradient-to-r from-purple-500 to-indigo-500 '
                    'hover:from-purple-600 hover:to-indigo-600 shadow-lg'
                )
                clear_btn = ui.button(icon='delete').classes(
                    'w-16 h-16 bg-red-500/20 text-red-400 hover:bg-red-500/40 shadow-lg'
                ).tooltip('Clear Image')

            # Visual History Grid button
            history_btn = ui.button('Visual History Grid', icon='photo_library').classes(
                'w-full h-12 bg-white/5 hover:bg-white/10 '
                'text-white/70 border border-white/10 shadow'
            )

    _grid_open = {'value': False}
    _grid_element = {'ref': None}

    _gen_state = {
        'active': False,
        'idx': 0,
        'total': 0,
        'pct': 0,
        'batch_prefix': '',
        'spinner_cell': None,
        'circ_progress': None,
        'linear_progress': None,
        'progress_label': None,
    }

    def _inject_grid_spinner():
        """Helper to inject a progress spinner into the history grid if active."""
        if not _gen_state['active'] or not _grid_open['value'] or _grid_element['ref'] is None:
            return
        
        grid = _grid_element['ref']
        with grid:
            with ui.element('div').style(
                'position: relative; overflow: hidden;'
                'aspect-ratio: 1 / 1; background: rgba(88,28,135,0.25);'
                'border: 1px solid rgba(168,85,247,0.4);'
                'border-radius: 6px;'
                'display: flex; flex-direction: column;'
                'align-items: center; justify-content: center; gap: 6px;'
            ) as spinner_cell:
                _gen_state['spinner_cell'] = spinner_cell
                _gen_state['circ_progress'] = ui.circular_progress(
                    min=0, max=100, value=_gen_state['pct'], show_value=True, size='56px'
                ).props('color=purple track-color=white/10 font-size=10px')
                ui.label(f"{_gen_state['batch_prefix']}Generating…").style(
                    'font-size: 11px; color: rgba(216,180,254,0.7);'
                    'font-family: monospace; letter-spacing: 0.05em;'
                )
        spinner_cell.move(grid, 0)

    def _inject_normal_progress():
        """Helper to inject a linear progress bar into the main view if active."""
        if not _gen_state['active'] or _grid_open['value']:
            return
            
        image_container.clear()
        with image_container:
            with ui.column().classes('items-center justify-center gap-4 w-full px-12'):
                ui.icon('auto_awesome', size='48px').classes('text-purple-400/60 mb-2')
                _gen_state['progress_label'] = ui.label(f"{_gen_state['batch_prefix']}Preparing…").classes(
                    'text-white/50 text-sm font-mono tracking-widest'
                )
                _gen_state['linear_progress'] = ui.linear_progress(
                    value=_gen_state['pct']/100, size='12px', show_value=False
                ).classes('w-full').props('rounded color=purple')
                ui.label(f"Generating image {_gen_state['idx']+1} of {_gen_state['total']} — this may take a moment").classes(
                    'text-white/20 text-xs mt-1'
                )

    # ── Helper: restore the "no image" placeholder ───────────────────────────
    def show_placeholder():
        _grid_open['value'] = False
        _grid_element['ref'] = None
        image_container.clear()
        with image_container:
            ui.icon('image', size='64px').classes('text-white/10 mb-4')
            ui.label('Generated image will appear here').classes('text-white/30 text-lg')

    # ── Helper: show a single image full-size inside image_container ─────────
    def show_image(path: str):
        """path is the web-accessible URL string (e.g. '/data/visual/foo.png')."""
        _grid_open['value'] = False
        _grid_element['ref'] = None
        image_container.clear()
        with image_container:
            ui.image(path).classes('w-full h-full object-contain')

    # ── Helper: open the history grid inside image_container ─────────────────
    def show_history():
        _grid_open['value'] = True
        image_container.clear()
        with image_container:
            # Header bar
            with ui.row().classes('w-full items-center justify-between px-4 pt-3 pb-1').style(
                'flex-shrink: 0;'
            ):
                ui.label('Generation History').classes(
                    'text-white/60 text-sm font-semibold uppercase tracking-widest'
                )
                ui.button(icon='close', on_click=_restore_last).props('flat dense').classes(
                    'text-white/40 hover:text-white/80'
                ).tooltip('Back to current image')

            if not os.path.isdir(_VISUAL_DIR):
                ui.label('No images found.').classes('text-white/30 m-auto')
                return

            images = sorted(
                [f for f in os.listdir(_VISUAL_DIR)
                 if os.path.splitext(f)[1].lower() in _VISUAL_EXTS],
                reverse=True,
            )

            if not images:
                ui.label('No images yet.').classes('text-white/30 m-auto')
                return

            # Scrollable grid
            with ui.element('div').style(
                'width: 100%;'
                'overflow-y: auto;'
                'flex: 1;'
                'padding: 8px 12px 12px;'
            ):
                grid = ui.element('div').style(
                    'display: grid;'
                    'grid-template-columns: repeat(5, 1fr);'
                    'gap: 8px;'
                )
                _grid_element['ref'] = grid
                with grid:
                    for fname in images:
                        src = f'/{_VISUAL_DIR}/{fname}'
                        fpath = f'{_VISUAL_DIR}/{fname}'
                        _add_grid_cell(grid, src, fpath)
        
        # Re-inject spinner if needed
        _inject_grid_spinner()

    # ── Helper: delete an image file and refresh the grid ───────────────────
    def _delete_image(fpath: str):
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
            last = app.storage.user.get('visual_last_image')
            if last and os.path.normpath(last) == os.path.normpath(fpath):
                app.storage.user['visual_last_image'] = None
            # Notify BEFORE show_history() — which calls image_container.clear()
            # and destroys the current slot context, breaking ui.notify afterwards.
            ui.notify('Image deleted.', type='info')
            show_history()
        except Exception as exc:
            ui.notify(f'Could not delete image: {exc}', type='negative')

    # ── Helper: add a hover-reveal delete button to an existing cell div ─────
    def _add_delete_btn(cell_div, fpath: str):
        with cell_div:
            btn = ui.button(icon='delete').props('flat dense round').style(
                'position: absolute; top: 4px; right: 4px;'
                'width: 26px; height: 26px; min-height: unset;'
                'background: rgba(220,38,38,0.75);'
                'color: white; opacity: 0;'
                'transition: opacity 0.15s ease;'
                'z-index: 10;'
            ).classes('text-xs')
            btn.on('click.stop', lambda p=fpath: _delete_image(p))
            # Show on parent hover via JS
            cell_div.on('mouseover', lambda b=btn: b.style(
                'position: absolute; top: 4px; right: 4px;'
                'width: 26px; height: 26px; min-height: unset;'
                'background: rgba(220,38,38,0.75);'
                'color: white; opacity: 1;'
                'transition: opacity 0.15s ease;'
                'z-index: 10;'
            ))
            cell_div.on('mouseout', lambda b=btn: b.style(
                'position: absolute; top: 4px; right: 4px;'
                'width: 26px; height: 26px; min-height: unset;'
                'background: rgba(220,38,38,0.75);'
                'color: white; opacity: 0;'
                'transition: opacity 0.15s ease;'
                'z-index: 10;'
            ))

    # ── Helper: build a full grid cell (image + delete button) ───────────────
    def _add_grid_cell(grid, src: str, fpath: str):
        with grid:
            cell = ui.element('div').style(
                'position: relative; overflow: hidden; cursor: pointer;'
                'aspect-ratio: 1 / 1; background: rgba(0,0,0,0.3);'
                'transition: transform 0.15s ease, box-shadow 0.15s ease;'
            )
            cell.on('click', lambda s=src: show_image(s))
            with cell:
                ui.image(src).style(
                    'width:100%; height:100%; object-fit:cover; display:block;'
                )
            _add_delete_btn(cell, fpath)

    def _restore_last():
        """Go back to the last generated image (or placeholder)."""
        _grid_open['value'] = False
        _grid_element['ref'] = None
        
        if _gen_state['active']:
            _inject_normal_progress()
            return
            
        last = app.storage.user.get('visual_last_image')
        if last and os.path.exists(last):
            show_image(f'/{last}')
        else:
            show_placeholder()

    history_btn.on('click', show_history)

    # ── Generate handler ─────────────────────────────────────────────────────
    async def on_generate():
        gui_client = ui.context.client
        def safe_notify(msg, **kwargs):
            try:
                gui_client.notify(msg, **kwargs)
            except Exception:
                pass

        # Free up VRAM by unloading any active LLMs
        try:
            from utils.llm_client import client as llm_client
            await llm_client.unload_all_models()
        except Exception as e:
            print(f"Failed to unload LLMs before visual generation: {e}")

        raw_prompts = [p.strip() for p in prompt.value.split('///') if p.strip()]
        if not raw_prompts:
            safe_notify('Please enter a positive prompt', type='warning')
            return

        generate_btn.disable()
        total_prompts = len(raw_prompts)
        
        # Reset state
        _gen_state['active'] = True
        _gen_state['total'] = total_prompts
        _gen_state['pct'] = 0
        
        loop = asyncio.get_event_loop()

        def on_progress(step: int, total: int):
            if total == 0:
                return
            pct = min(round(step / total * 100), 100)
            _gen_state['pct'] = pct
            
            def _update():
                try:
                    if _gen_state['circ_progress']:
                        _gen_state['circ_progress'].set_value(pct)
                    if _gen_state['linear_progress']:
                        _gen_state['linear_progress'].set_value(pct / 100)
                    if _gen_state['progress_label']:
                        _gen_state['progress_label'].set_text(f"{_gen_state['batch_prefix']}Step {step} / {total}")
                except Exception:
                    pass
            loop.call_soon_threadsafe(_update)

        try:
            for idx, current_p in enumerate(raw_prompts):
                _gen_state['idx'] = idx
                _gen_state['batch_prefix'] = f"[{idx + 1}/{total_prompts}] " if total_prompts > 1 else ""
                _gen_state['pct'] = 0
                
                # Clear UI refs (they will be re-injected if we are in the right view)
                _gen_state['spinner_cell'] = None
                _gen_state['circ_progress'] = None
                _gen_state['linear_progress'] = None
                _gen_state['progress_label'] = None

                if _grid_open['value']:
                    _inject_grid_spinner()
                else:
                    _inject_normal_progress()

                try:
                    w_str, h_str = image_size.value.split('x')
                    output_path = await run.io_bound(
                        generate_image_task,
                        current_p, negative_prompt.value,
                        int(steps.value), int(w_str), int(h_str),
                        on_progress,
                        unload_after=(idx == total_prompts - 1)
                    )
                    app.storage.user['visual_last_image'] = output_path
                    src = f'/{output_path}'
                    
                    # Handle completion UI
                    if _gen_state['spinner_cell']:
                        cell = _gen_state['spinner_cell']
                        cell.clear()
                        cell.style(
                            'position: relative; overflow: hidden;'
                            'aspect-ratio: 1 / 1; background: rgba(0,0,0,0.3);'
                            'border: none; border-radius: 6px; cursor: pointer;'
                            'display: block;'
                        )
                        with cell:
                            ui.image(src).style('width:100%; height:100%; object-fit:cover; display:block;')
                            _add_delete_btn(cell, output_path)
                        cell.on('click', lambda s=src: show_image(s))
                    
                    if not _grid_open['value']:
                        image_container.clear()
                        with image_container:
                            ui.image(f'/{output_path}').classes('w-full h-full object-contain rounded-lg shadow-xl')

                    if total_prompts == 1:
                        safe_notify('Image generated successfully!', type='positive')
                    else:
                        safe_notify(f'Generated {idx+1}/{total_prompts}', type='positive', pos='bottom-right', timeout=2000)

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    if _gen_state['spinner_cell']:
                        _gen_state['spinner_cell'].delete()
                    safe_notify(f'Failed to generate image {idx+1}: {str(e)}', type='negative')
        
        finally:
            _gen_state['active'] = False
            _gen_state['spinner_cell'] = None
            _gen_state['circ_progress'] = None
            _gen_state['linear_progress'] = None
            _gen_state['progress_label'] = None
            generate_btn.enable()
            if total_prompts > 1:
                safe_notify(f'Batch processing of {total_prompts} prompts complete.', type='info')

    def on_clear():
        app.storage.user['visual_last_image'] = None
        show_placeholder()

    generate_btn.on('click', on_generate)
    clear_btn.on('click', on_clear)
