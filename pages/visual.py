import os
import asyncio
from nicegui import ui, run, app
from services.visual_service import generate_image_task


_VISUAL_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
_VISUAL_DIR  = 'data/visual'


_grid_open = {'value': True}
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
    'image_container': None,
    'client': None,
}

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
    if 'visual_batch_count' not in app.storage.user:
        app.storage.user['visual_batch_count'] = 1

    # ── Main two-column layout ───────────────────────────────────────────────
    with ui.row().classes('w-full max-w-screen-2xl mx-auto gap-6 p-4 flex-nowrap items-start'):

        # Left column – image area (70%)
        with ui.column().classes(
            'rounded-lg border border-white/10 overflow-hidden bg-black/20 '
            'relative'
        ).style('flex: 7; height: calc(100vh - 120px); min-height: 500px;') as image_container:
            _gen_state['image_container'] = image_container
            _gen_state['client'] = ui.context.client
            _gen_state['full_view_container'] = ui.element('div').classes('w-full h-full flex flex-col items-center justify-center hidden')
            _gen_state['grid_view_container'] = ui.element('div').classes('w-full h-full flex flex-col hidden')
            _grid_element['ref'] = None
            pass

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

            with ui.row().classes('w-full gap-4 flex-nowrap'):
                with ui.column().classes('flex-grow gap-1'):
                    ui.label('Image Size').classes('text-sm text-gray-400')
                    image_size = ui.select(
                        options={
                            '1024x1024': '1024 × 1024 (1:1)',
                            '896x1152':  '896 × 1152 (3:4)',
                            '1152x896':  '1152 × 896 (4:3)',
                        }
                    ).classes('w-full').bind_value(app.storage.user, 'visual_image_size')
                
                with ui.column().classes('w-24 gap-1'):
                    ui.label('Count').classes('text-sm text-gray-400')
                    batch_count = ui.number(value=1, min=1, max=50, format='%d').classes('w-full').bind_value(app.storage.user, 'visual_batch_count')

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

            # Generate
            with ui.row().classes('w-full gap-4 mt-2 flex-nowrap'):
                generate_btn = ui.button('Generate', icon='brush').classes(
                    'w-full h-16 text-xl transition-all duration-300 '
                    'bg-gradient-to-r from-purple-500 to-indigo-500 '
                    'hover:from-purple-600 hover:to-indigo-600 shadow-lg'
                )

            pass

    # State is now managed at the module level

    def _inject_grid_spinner():
        """Helper to inject a progress spinner into the history grid if active."""
        if not _gen_state['active'] or _grid_element['ref'] is None:
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
            
        full_view = _gen_state.get('full_view_container')
        if not full_view: return
        full_view.clear()
        with full_view:
            with ui.column().classes('relative items-center justify-center gap-4 w-full h-full px-12'):
                ui.button(icon='grid_view', on_click=show_history).props('flat dense round').style(
                    'position: absolute; top: 16px; right: 16px;'
                    'width: 40px; height: 40px; background: rgba(0,0,0,0.5); color: white; z-index: 10;'
                ).tooltip('Visual History Grid')
                
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
        full_view = _gen_state.get('full_view_container')
        grid_view = _gen_state.get('grid_view_container')
        if not full_view or not grid_view: return
        
        grid_view.classes(add='hidden')
        full_view.classes(remove='hidden')
        full_view.clear()
        with full_view:
            with ui.column().classes('relative w-full h-full items-center justify-center'):
                ui.button(icon='grid_view', on_click=show_history).props('flat dense round').style(
                    'position: absolute; top: 16px; right: 16px;'
                    'width: 40px; height: 40px; background: rgba(0,0,0,0.5); color: white; z-index: 10;'
                ).tooltip('Visual History Grid')
                
                ui.icon('image', size='64px').classes('text-white/10 mb-4')
                ui.label('Generated image will appear here').classes('text-white/30 text-lg')

    # ── Helper: render full image with navigation ────────────────────────────
    def _render_image_with_nav(path: str):
        images = []
        if os.path.isdir(_VISUAL_DIR):
            images = sorted(
                [f for f in os.listdir(_VISUAL_DIR)
                 if os.path.isfile(os.path.join(_VISUAL_DIR, f)) and os.path.splitext(f)[1].lower() in _VISUAL_EXTS],
                reverse=True,
            )
            
        filename = path.split('/')[-1]
        prev_img = None
        next_img = None
        
        try:
            idx = images.index(filename)
            if idx > 0:
                prev_img = f"/{_VISUAL_DIR}/{images[idx - 1]}"
            if idx < len(images) - 1:
                next_img = f"/{_VISUAL_DIR}/{images[idx + 1]}"
        except ValueError:
            pass

        with ui.element('div').classes('w-full h-full relative group') as img_div:
            with ui.element('div').classes('w-full h-full overflow-auto flex flex-col'):
                img = ui.element('img').props(f'src="{path}"').classes('m-auto w-full h-full object-contain rounded-lg shadow-xl transition-all duration-300')
            
            fpath = path.lstrip('/')
            _add_delete_btn(img_div, fpath)
            _add_regenerate_btn(img_div, fpath)
            _add_info_btn(img_div, fpath)
            
            zoom_state = {'fit': True}
            
            with ui.row().classes(
                'absolute left-1/2 -translate-x-1/2 flex items-center gap-2 '
                'opacity-0 group-hover:opacity-100 transition-opacity z-10'
            ).style('top: 4px;'):
                def toggle_zoom():
                    if zoom_state['fit']:
                        img.classes(remove='h-full object-contain', add='h-auto')
                        zoom_btn.props('icon=zoom_out')
                        zoom_state['fit'] = False
                    else:
                        img.classes(remove='h-auto', add='h-full object-contain')
                        zoom_btn.props('icon=zoom_in')
                        zoom_state['fit'] = True
                        
                zoom_btn = ui.button(icon='zoom_in', on_click=toggle_zoom).props('flat dense round').style(
                    'width: 26px; height: 26px; min-height: unset;'
                    'background: rgba(0,0,0,0.75); color: white;'
                ).classes('text-xs').tooltip('Toggle Zoom')
                
                ui.button(icon='grid_view', on_click=show_history).props('flat dense round').style(
                    'width: 26px; height: 26px; min-height: unset;'
                    'background: rgba(0,0,0,0.75); color: white;'
                ).classes('text-xs').tooltip('Visual History Grid')
            
            if prev_img:
                ui.button(icon='chevron_left', on_click=lambda p=prev_img: show_image(p)).props('round flat size=lg').classes(
                    'absolute left-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white hover:bg-black/80 z-10'
                )
            if next_img:
                ui.button(icon='chevron_right', on_click=lambda n=next_img: show_image(n)).props('round flat size=lg').classes(
                    'absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white hover:bg-black/80 z-10'
                )

    # ── Helper: show a single image full-size inside image_container ─────────
    def show_image(path: str):
        """path is the web-accessible URL string (e.g. '/data/visual/foo.png')."""
        _grid_open['value'] = False
        full_view = _gen_state.get('full_view_container')
        grid_view = _gen_state.get('grid_view_container')
        if not full_view or not grid_view: return
        
        grid_view.classes(add='hidden')
        full_view.classes(remove='hidden')
        full_view.clear()
        with full_view:
            _render_image_with_nav(path)

    # ── Helper: open the history grid inside image_container ─────────────────
    def show_history():
        _grid_open['value'] = True
        full_view = _gen_state.get('full_view_container')
        grid_view = _gen_state.get('grid_view_container')
        if not full_view or not grid_view: return
        
        full_view.classes(add='hidden')
        grid_view.classes(remove='hidden')
        
        if _grid_element.get('ref') is not None:
            return  # Grid already built

        grid_view.clear()
        with grid_view:
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
                 if os.path.isfile(os.path.join(_VISUAL_DIR, f)) and os.path.splitext(f)[1].lower() in _VISUAL_EXTS],
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
                    os.makedirs(f"{_VISUAL_DIR}/thumbs", exist_ok=True)
                    for fname in images:
                        fpath = f'{_VISUAL_DIR}/{fname}'
                        src = f'/{fpath}'
                        thumb_path = f'{_VISUAL_DIR}/thumbs/{fname}'
                        
                        if not os.path.exists(thumb_path):
                            try:
                                from PIL import Image
                                with Image.open(fpath) as img:
                                    img.thumbnail((256, 256))
                                    img.save(thumb_path)
                            except Exception:
                                pass
                                
                        thumb_src = f'/{thumb_path}' if os.path.exists(thumb_path) else src
                        _add_grid_cell(grid, thumb_src, src, fpath)
        
        # Re-inject spinner if needed
        _inject_grid_spinner()

    # ── Helper: delete an image file and refresh the grid ───────────────────
    def _delete_image(fpath: str, cell_div=None):
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
                dirname, fname = os.path.split(fpath)
                thumb_path = f"{dirname}/thumbs/{fname}".replace('\\', '/')
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
            last = app.storage.user.get('visual_last_image')
            if last and os.path.normpath(last) == os.path.normpath(fpath):
                app.storage.user['visual_last_image'] = None
                
            ui.notify('Image deleted.', type='info')
            
            if _grid_open['value'] and cell_div:
                cell_div.delete()
            elif not _grid_open['value']:
                show_placeholder()
                _grid_element['ref'] = None  # Force rebuild next time grid is opened
                
        except Exception as exc:
            ui.notify(f'Could not delete image: {exc}', type='negative')

    # ── Helper: add a hover-reveal delete button to an existing cell div ─────
    def _add_delete_btn(cell_div, fpath: str):
        with cell_div:
            btn = ui.button(icon='delete').props('flat dense round').style(
                'position: absolute; bottom: 4px; left: 4px;'
                'width: 26px; height: 26px; min-height: unset;'
                'background: rgba(0,0,0,0.75);'
                'color: white;'
                'transition: opacity 0.15s ease;'
                'z-index: 10;'
            ).classes('text-xs opacity-0 group-hover:opacity-100')
            btn.on('click.stop', lambda p=fpath, c=cell_div: _delete_image(p, c))

    async def _regenerate_image(fpath: str):
        try:
            from PIL import Image
            import json
            with Image.open(fpath) as img:
                metadata = img.text if hasattr(img, 'text') else img.info
                params_str = metadata.get('parameters')
                if not params_str:
                    ui.notify('No generation metadata found in this image.', type='warning')
                    return
                params = json.loads(params_str)
            
            prompt.value = params.get('prompt', '')
            negative_prompt.value = params.get('negative_prompt', '')
            steps.value = params.get('steps', 30)
            w = params.get('width', 1024)
            h = params.get('height', 1024)
            image_size.value = f"{w}x{h}"
            
            ui.notify('Regenerating from metadata...', type='info')
            
            await on_generate()
            
        except Exception as e:
            ui.notify(f"Could not read metadata: {e}", type='negative')

    def _add_regenerate_btn(cell_div, fpath: str):
        with cell_div:
            btn = ui.button(icon='refresh').props('flat dense round').style(
                'position: absolute; top: 4px; left: 4px;'
                'width: 26px; height: 26px; min-height: unset;'
                'background: rgba(0,0,0,0.75);'
                'color: white;'
                'transition: opacity 0.15s ease;'
                'z-index: 10;'
            ).classes('text-xs opacity-0 group-hover:opacity-100').tooltip('Regenerate')
            btn.on('click.stop', lambda p=fpath: _regenerate_image(p))

    def _load_metadata(fpath: str):
        try:
            from PIL import Image
            import json
            with Image.open(fpath) as img:
                metadata = img.text if hasattr(img, 'text') else img.info
                params_str = metadata.get('parameters')
                if not params_str:
                    ui.notify('No generation metadata found in this image.', type='warning')
                    return
                params = json.loads(params_str)
            
            prompt.value = params.get('prompt', '')
            negative_prompt.value = params.get('negative_prompt', '')
            steps.value = params.get('steps', 30)
            w = params.get('width', 1024)
            h = params.get('height', 1024)
            image_size.value = f"{w}x{h}"
            
            ui.notify('Parameters loaded from metadata.', type='info')
            
        except Exception as e:
            ui.notify(f"Could not read metadata: {e}", type='negative')

    def _add_info_btn(cell_div, fpath: str):
        with cell_div:
            btn = ui.button(icon='info').props('flat dense round').style(
                'position: absolute; top: 4px; right: 4px;'
                'width: 26px; height: 26px; min-height: unset;'
                'background: rgba(0,0,0,0.75);'
                'color: white;'
                'transition: opacity 0.15s ease;'
                'z-index: 10;'
            ).classes('text-xs opacity-0 group-hover:opacity-100').tooltip('Load Parameters')
            btn.on('click.stop', lambda p=fpath: _load_metadata(p))

    # ── Helper: build a full grid cell (image + delete button) ───────────────
    def _add_grid_cell(grid, thumb_src: str, full_src: str, fpath: str):
        with grid:
            cell = ui.element('div').classes('group').style(
                'position: relative; overflow: hidden; cursor: pointer;'
                'aspect-ratio: 1 / 1; background: rgba(0,0,0,0.3);'
                'transition: transform 0.15s ease, box-shadow 0.15s ease;'
            )
            cell.on('click', lambda s=full_src: show_image(s))
            with cell:
                ui.image(thumb_src).style(
                    'width:100%; height:100%; object-fit:cover; display:block;'
                )
            _add_delete_btn(cell, fpath)
            _add_regenerate_btn(cell, fpath)
            _add_info_btn(cell, fpath)

    def _restore_last():
        """Go back to the last generated image (or placeholder)."""
        _grid_open['value'] = False
        
        if _gen_state['active']:
            _inject_normal_progress()
            return
            
        last = app.storage.user.get('visual_last_image')
        if last and os.path.exists(last):
            show_image(f'/{last}')
        else:
            show_placeholder()

    if _grid_open['value']:
        show_history()
    elif _gen_state['active']:
        _inject_normal_progress()
    else:
        last = app.storage.user.get('visual_last_image')
        if last and os.path.exists(last):
            show_image(f'/{last}')
        else:
            show_placeholder()
        
    if _gen_state['active']:
        generate_btn.props('color=red icon=stop')
        generate_btn.set_text('Stop')
        generate_btn.classes(remove='from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600', add='from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600')

    # ── Generate handler ─────────────────────────────────────────────────────
    async def on_generate():
        def safe_notify(msg, **kwargs):
            try:
                client = _gen_state.get('client')
                if client and not client._deleted:
                    client.notify(msg, **kwargs)
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

        batch_count = int(app.storage.user.get('visual_batch_count', 1))
        expanded_prompts = []
        for p in raw_prompts:
            expanded_prompts.extend([p] * batch_count)
        raw_prompts = expanded_prompts

        total_prompts = len(raw_prompts)
        
        # Reset state
        _gen_state['active'] = True
        _gen_state['cancel'] = False
        _gen_state['total'] = total_prompts
        _gen_state['pct'] = 0
        
        generate_btn.props('color=red icon=stop')
        generate_btn.set_text('Stop')
        generate_btn.classes(remove='from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600', add='from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600')
        
        loop = asyncio.get_event_loop()

        def on_progress(step: int, total: int):
            if _gen_state.get('cancel'):
                return "CANCEL"
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

                _inject_grid_spinner()
                if not _grid_open['value']:
                    _inject_normal_progress()

                try:
                    w_str, h_str = image_size.value.split('x')
                    output_path = await run.io_bound(
                        generate_image_task,
                        current_p,
                        negative_prompt.value,
                        app.storage.user['visual_inference_steps'],
                        int(w_str),
                        int(h_str),
                        on_progress,
                        unload_after=False
                    )
                    
                    if not output_path:
                        if _gen_state.get('cancel'):
                            if _gen_state['spinner_cell']:
                                _gen_state['spinner_cell'].delete()
                            break
                        raise Exception("Pipeline returned None")
                        
                    app.storage.user['visual_last_image'] = output_path
                    src = f'/{output_path}'
                    
                    dirname, fname = os.path.split(output_path)
                    thumb_path = f"{dirname}/thumbs/{fname}".replace('\\', '/')
                    thumb_src = f'/{thumb_path}' if os.path.exists(thumb_path) else src
                    
                    # Handle completion UI
                    if _gen_state['spinner_cell']:
                        cell = _gen_state['spinner_cell']
                        cell.clear()
                        cell.style(
                            'position: relative; overflow: hidden;'
                            'aspect-ratio: 1 / 1; background: rgba(0,0,0,0.3);'
                            'border: none; border-radius: 6px; cursor: pointer;'
                            'display: block;'
                        ).classes('group')
                        with cell:
                            ui.image(thumb_src).style('width:100%; height:100%; object-fit:cover; display:block;')
                            _add_delete_btn(cell, output_path)
                            _add_regenerate_btn(cell, output_path)
                            _add_info_btn(cell, output_path)
                        cell.on('click', lambda s=src: show_image(s))
                    
                    if not _grid_open['value']:
                        container = _gen_state.get('image_container')
                        if container:
                            show_image(f'/{output_path}')

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
            # Always ensure the visual pipeline is unloaded when generation finishes or fails
            try:
                from services.visual_service import unload_pipeline
                await run.io_bound(unload_pipeline)
            except Exception as e:
                print(f"Failed to unload visual pipeline in finally block: {e}")

            _gen_state['active'] = False
            _gen_state['cancel'] = False
            _gen_state['spinner_cell'] = None
            _gen_state['circ_progress'] = None
            _gen_state['linear_progress'] = None
            _gen_state['progress_label'] = None
            generate_btn.enable()
            generate_btn.props('color=primary icon=brush')
            generate_btn.set_text('Generate')
            generate_btn.classes(add='from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600', remove='from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600')
            
            if not _grid_open['value']:
                last = app.storage.user.get('visual_last_image')
                if last and os.path.exists(last):
                    show_image(f'/{last}')
                else:
                    show_placeholder()
            
            if _gen_state.get('cancel'):
                safe_notify('Generation stopped.', type='warning')
            elif total_prompts > 1:
                safe_notify(f'Batch processing of {total_prompts} prompts complete.', type='info')

    async def on_generate_click():
        if _gen_state.get('active'):
            _gen_state['cancel'] = True
            generate_btn.set_text('Stopping...')
            generate_btn.disable()
        else:
            await on_generate()

    generate_btn.on('click', on_generate_click)
