import os
import asyncio
from nicegui import ui, run, app
from services.visual_service import generate_image_task
from utils.config import config_manager


_VISUAL_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
_VISUAL_DIR  = 'data/visual/images'
_CHECKER_BG = (
    'background-color: #1f2937;'
    'background-image: '
    'linear-gradient(45deg, rgba(255,255,255,0.16) 25%, transparent 25%),'
    'linear-gradient(-45deg, rgba(255,255,255,0.16) 25%, transparent 25%),'
    'linear-gradient(45deg, transparent 75%, rgba(255,255,255,0.16) 75%),'
    'linear-gradient(-45deg, transparent 75%, rgba(255,255,255,0.16) 75%);'
    'background-size: 24px 24px;'
    'background-position: 0 0, 0 12px, 12px -12px, -12px 0;'
)


_grid_open = {'value': True}
_grid_element = {'ref': None}
_page_state = {
    'current_page': 1,
    'page_size': 25,
}
_selection_state = {
    'active': False,
    'selected': set(),
    'cells': {},
    'toggle_btn': None,
    'delete_btn': None,
    'hide_btn': None,
    'count_label': None,
}
_initialized_users = set()
_view_state = {
    'current_image': None,
}
_rembg_state = {
    'session': None,
    'model': None,
}

_gen_state = {
    'active': False,
    'idx': 0,
    'total': 0,
    'pct': 0,
    'batch_prefix': '',
    'image_container': None,
    'client': None,
    'global_idx': 0,
    'global_total': 0,
    'generate_btn': None,
    'queue_btn': None,
    'remove_bg_btn': None,
    'remove_bg_status': None,
    'progress_sidebar': None,
    'progress_sidebar_label': None,
    'progress_sidebar_bar': None,
    'preview_image': None,
    'show_history': None,
    'show_image': None,
    'show_placeholder': None,
    'inject_preview_canvas': None,
    'update_progress_labels': None,
}

_generation_queue = []

def create_page():
    page_client = ui.context.client

    def _notify(msg, **kwargs):
        try:
            if page_client and not page_client._deleted:
                page_client.notify(msg, **kwargs)
        except Exception:
            pass

    def _set_remove_background_busy(active: bool):
        try:
            if active:
                remove_bg_btn.disable()
                remove_bg_btn.set_text('Working...')
                remove_bg_btn.props('loading')
                remove_bg_status.set_text('Remove BG is working...')
                remove_bg_status.classes(remove='hidden')
            else:
                remove_bg_btn.enable()
                remove_bg_btn.set_text('Remove BG')
                remove_bg_btn.props(remove='loading')
                remove_bg_status.set_text('')
                remove_bg_status.classes(add='hidden')
        except Exception:
            pass

    def _open_remove_background_dialog():
        remove_bg_model_input.options = app.storage.user.get('visual_remove_background_models', ['isnet-anime'])
        remove_bg_model_input.update()
        remove_bg_model_input.value = app.storage.user.get('visual_remove_background_model', 'isnet-anime')
        remove_bg_dialog.open()

    def _remember_remove_background_model(model_name: str):
        models = app.storage.user.get('visual_remove_background_models', ['isnet-anime'])
        if not isinstance(models, list):
            models = ['isnet-anime']
        models = [m for m in models if isinstance(m, str) and m.strip()]
        if model_name not in models:
            models.append(model_name)
        app.storage.user['visual_remove_background_models'] = models
        app.storage.user['visual_remove_background_model'] = model_name
        try:
            remove_bg_model_input.options = models
            remove_bg_model_input.update()
        except Exception:
            pass

    async def _run_remove_background_from_dialog():
        model_name = (remove_bg_model_input.value or '').strip()
        if not model_name:
            _notify('Enter a rembg model name.', type='warning')
            return

        _remember_remove_background_model(model_name)
        remove_bg_dialog.close()
        await _run_remove_background_from_context(model_name=model_name)

    global _initialized_users
    user_id = app.storage.user.get('id') or 'default_user'
    if user_id not in _initialized_users:
        app.storage.user['visual_show_hidden'] = False
        _initialized_users.add(user_id)

    if 'visual_hidden_images' not in app.storage.user:
        app.storage.user['visual_hidden_images'] = []
    if 'visual_show_hidden' not in app.storage.user:
        app.storage.user['visual_show_hidden'] = False

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
    if 'visual_image_width' not in app.storage.user or 'visual_image_height' not in app.storage.user:
        old_size = app.storage.user.get('visual_image_size', '1024x1024')
        try:
            w_str, h_str = old_size.split('x')
            if 'visual_image_width' not in app.storage.user:
                app.storage.user['visual_image_width'] = int(w_str)
            if 'visual_image_height' not in app.storage.user:
                app.storage.user['visual_image_height'] = int(h_str)
        except Exception:
            if 'visual_image_width' not in app.storage.user:
                app.storage.user['visual_image_width'] = 1024
            if 'visual_image_height' not in app.storage.user:
                app.storage.user['visual_image_height'] = 1024
    if 'visual_inference_steps' not in app.storage.user:
        app.storage.user['visual_inference_steps'] = 30
    if 'visual_batch_count' not in app.storage.user:
        app.storage.user['visual_batch_count'] = 1
    if 'visual_remove_background_auto' not in app.storage.user:
        app.storage.user['visual_remove_background_auto'] = False
    if 'visual_generate_previews' not in app.storage.user:
        app.storage.user['visual_generate_previews'] = False
    if 'visual_remove_background_model' not in app.storage.user:
        app.storage.user['visual_remove_background_model'] = 'isnet-anime'
    if 'visual_remove_background_models' not in app.storage.user:
        app.storage.user['visual_remove_background_models'] = ['isnet-anime']
    elif not isinstance(app.storage.user['visual_remove_background_models'], list):
        app.storage.user['visual_remove_background_models'] = ['isnet-anime']
    if app.storage.user['visual_remove_background_model'] not in app.storage.user['visual_remove_background_models']:
        app.storage.user['visual_remove_background_models'].append(app.storage.user['visual_remove_background_model'])
    if 'visual_cfg_scale' not in app.storage.user:
        app.storage.user['visual_cfg_scale'] = 4.0
    if 'visual_turbo_lora_enabled' not in app.storage.user:
        app.storage.user['visual_turbo_lora_enabled'] = False
    if 'visual_turbo_lora_strength' not in app.storage.user:
        app.storage.user['visual_turbo_lora_strength'] = 1.0
    if 'visual_denoising_strength' not in app.storage.user:
        app.storage.user['visual_denoising_strength'] = 0.6

    # ── Main layout ──────────────────────────────────────────────────────────
    with ui.row().classes('w-full max-w-screen-2xl mx-auto gap-6 p-4 flex-nowrap items-start'):

        # Left column – image tools
        with ui.column().classes(
            'rounded-lg border border-white/10 bg-black/20 p-3 gap-3'
        ).style('flex: 1.35; height: calc(100vh - 120px); min-height: 500px;'):
            ui.label('Tools').classes('text-white/60 text-sm font-semibold uppercase tracking-widest')
            ui.separator().classes('bg-white/10')
            with ui.column().classes('w-full gap-2'):
                with ui.row().classes('w-full items-center gap-2 flex-nowrap'):
                    ui.checkbox().bind_value(
                        app.storage.user, 'visual_remove_background_auto'
                    ).tooltip('Run after image generation')
                    remove_bg_btn = ui.button(
                        'Remove BG',
                        icon='layers_clear',
                        on_click=_open_remove_background_dialog,
                    ).props('outline dense no-caps').classes('flex-1 text-sm').tooltip(
                        'Remove background from selected images or the current image'
                    )
                    _gen_state['remove_bg_btn'] = remove_bg_btn
                remove_bg_status = ui.label('').classes('hidden text-xs text-purple-300 font-mono')
                _gen_state['remove_bg_status'] = remove_bg_status

            with ui.dialog() as remove_bg_dialog, ui.card().classes('w-96 max-w-full gap-4'):
                ui.label('Remove Background').classes('text-lg font-semibold')
                remove_bg_model_input = ui.select(
                    app.storage.user['visual_remove_background_models'],
                    label='Model',
                    value=app.storage.user['visual_remove_background_model'],
                ).props('outlined dense use-input fill-input hide-selected new-value-mode=add').classes('w-full')
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=remove_bg_dialog.close).props('flat no-caps')
                    ui.button(
                        'Run',
                        icon='play_arrow',
                        on_click=_run_remove_background_from_dialog,
                    ).props('no-caps')

        # Center column – image area
        with ui.column().classes(
            'rounded-lg border border-white/10 overflow-hidden bg-black/20 '
            'relative'
        ).style('flex: 6.65; height: calc(100vh - 120px); min-height: 500px;') as image_container:
            _gen_state['image_container'] = image_container
            _gen_state['client'] = page_client
            _gen_state['full_view_container'] = ui.element('div').classes('w-full h-full flex flex-col items-center justify-center hidden')
            _gen_state['grid_view_container'] = ui.element('div').classes('w-full h-full flex flex-col hidden')
            _grid_element['ref'] = None
            pass

        # Right column – settings (30%)
        with ui.column().classes('gap-3').style('flex: 3;'):
            prompt = ui.textarea(
                'Positive Prompt', placeholder='masterpiece, best quality... (Use /// to separate multiple prompts)'
            ).classes('w-full text-sm').props('outlined rows="12"').bind_value(
                app.storage.user, 'visual_positive_prompt'
            )

            negative_prompt = ui.textarea(
                'Negative Prompt', placeholder='worst quality, low quality, …'
            ).classes('w-full text-sm').props('outlined rows="2"').bind_value(
                app.storage.user, 'visual_negative_prompt'
            )

            width_options = list(config_manager.config.get('visual_image_widths', [
                512, 576, 640, 704, 768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344, 1408, 1472, 1536
            ]))
            height_options = list(config_manager.config.get('visual_image_heights', [
                512, 576, 640, 704, 768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344, 1408, 1472, 1536
            ]))

            with ui.row().classes('w-full gap-4 flex-nowrap'):
                with ui.column().classes('flex-grow gap-1'):
                    ui.label('Width').classes('text-sm text-gray-400')
                    image_width = ui.select(
                        options=width_options
                    ).classes('w-full').bind_value(app.storage.user, 'visual_image_width')
                
                with ui.column().classes('flex-grow gap-1'):
                    ui.label('Height').classes('text-sm text-gray-400')
                    image_height = ui.select(
                        options=height_options
                    ).classes('w-full').bind_value(app.storage.user, 'visual_image_height')
                
                with ui.column().classes('w-20 gap-1'):
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

            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('CFG Scale').classes('text-sm text-gray-400')
                    cfg_scale_label = ui.label(
                        f"{app.storage.user.get('visual_cfg_scale', 4.0):.1f}"
                    ).classes('text-sm text-gray-300 font-mono')
                cfg_scale_slider = ui.slider(
                    min=1.0, max=20.0, step=0.1,
                    on_change=lambda e: cfg_scale_label.set_text(f"{e.value:.1f}")
                ).classes('w-full').bind_value(app.storage.user, 'visual_cfg_scale')

            with ui.row().classes('w-full items-center gap-2 flex-nowrap'):
                turbo_checkbox = ui.checkbox().bind_value(
                    app.storage.user, 'visual_turbo_lora_enabled'
                ).tooltip('Enable Turbo LoRA for faster generation (fewer steps needed)')
                ui.label('Turbo').classes('text-sm text-gray-400')
                turbo_strength_slider = ui.slider(
                    min=0.1, max=2.0, step=0.05
                ).classes('flex-grow').bind_value(
                    app.storage.user, 'visual_turbo_lora_strength'
                ).bind_enabled_from(
                    app.storage.user, 'visual_turbo_lora_enabled'
                )
                turbo_strength_label = ui.label().classes('text-sm text-gray-300 font-mono w-8 text-right')
                turbo_strength_label.bind_text_from(
                    turbo_strength_slider, 'value', backward=lambda v: f"{v:.2f}"
                )

            ui.checkbox('Generate Intermediate Previews').bind_value(
                app.storage.user, 'visual_generate_previews'
            ).tooltip('Generate and show intermediate preview images (increases VRAM usage during generation)')

            # Generate
            with ui.row().classes('w-full gap-4 mt-2 flex-nowrap items-center'):
                generate_btn = ui.button('Generate', icon='brush').classes(
                    'w-full h-12 text-lg transition-all duration-300 '
                    'bg-gradient-to-r from-purple-500 to-indigo-500 '
                    'hover:from-purple-600 hover:to-indigo-600 shadow-lg'
                ).style('flex: 4;')
                _gen_state['generate_btn'] = generate_btn
                
                queue_btn = ui.button(icon='queue_play_next').props('outline').classes(
                    'h-12 text-md transition-all duration-300'
                ).style('flex: 1; min-width: 64px;').tooltip('Queue Generation')
                _gen_state['queue_btn'] = queue_btn

            # Denoising and i2i button
            with ui.row().classes('w-full gap-4 mt-2 flex-nowrap items-center'):
                with ui.column().classes('flex-grow gap-0'):
                    with ui.row().classes('w-full justify-between items-center'):
                        ui.label('Denoising Strength').classes('text-sm text-gray-400')
                        denoising_label = ui.label(
                            f"{app.storage.user.get('visual_denoising_strength', 0.6):.2f}"
                        ).classes('text-sm text-gray-300 font-mono')
                    denoising_slider = ui.slider(
                        min=0.01, max=1.0, step=0.01,
                        on_change=lambda e: denoising_label.set_text(f"{e.value:.2f}")
                    ).classes('w-full').bind_value(app.storage.user, 'visual_denoising_strength')
                
                itoi_btn = ui.button('i2i', icon='image').classes(
                    'h-12 text-md transition-all duration-300 '
                    'bg-gradient-to-r from-teal-500 to-emerald-500 '
                    'hover:from-teal-600 hover:to-emerald-600 shadow-lg'
                ).style('flex: 0 0 auto; width: 90px;').tooltip('Image to Image (itoi) Generation')
                _gen_state['itoi_btn'] = itoi_btn

            # Progress section below generate/queue buttons
            progress_sidebar = ui.column().classes('w-full gap-2 mt-2 hidden')
            with progress_sidebar:
                progress_sidebar_label = ui.label('Generating 0 of 0').classes('text-sm text-gray-300 font-medium')
                progress_sidebar_bar = ui.linear_progress(value=0, show_value=False).classes('w-full').props('rounded color=purple')
            _gen_state['progress_sidebar'] = progress_sidebar
            _gen_state['progress_sidebar_label'] = progress_sidebar_label
            _gen_state['progress_sidebar_bar'] = progress_sidebar_bar

    # State is now managed at the module level

    def _inject_preview_canvas():
        """Helper to inject a clean preview image container into the main view if active."""
        if page_client._deleted or not _gen_state['active'] or _grid_open['value']:
            return
            
        full_view = _gen_state.get('full_view_container')
        grid_view = _gen_state.get('grid_view_container')
        if not full_view or not grid_view: return
        
        grid_view.classes(add='hidden')
        full_view.classes(remove='hidden')
        
        if _view_state['current_image']:
            return
            
        full_view.clear()
        with full_view:
            with ui.element('div').classes('w-full h-full relative'):
                ui.button(icon='grid_view', on_click=show_history).props('flat dense round').style(
                    'position: absolute; top: 16px; right: 16px;'
                    'width: 40px; height: 40px; background: rgba(0,0,0,0.5); color: white; z-index: 10;'
                ).tooltip('Visual History Grid')
                with ui.element('div').classes('w-full h-full overflow-auto flex flex-col').style(_CHECKER_BG):
                    _gen_state['preview_image'] = ui.element('img').props('src=""').classes(
                        'm-auto w-full h-full object-contain rounded-lg shadow-xl hidden transition-all duration-300'
                    )

    # ── Helper: restore the "no image" placeholder ───────────────────────────
    def show_placeholder():
        if page_client._deleted:
            return
        _grid_open['value'] = False
        _view_state['current_image'] = None
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
        hidden_images = app.storage.user.get('visual_hidden_images', [])
        if not isinstance(hidden_images, list):
            hidden_images = []
        hidden_set = set(hidden_images)

        images = []
        if os.path.isdir(_VISUAL_DIR):
            all_files = sorted(
                [f for f in os.listdir(_VISUAL_DIR)
                 if os.path.isfile(os.path.join(_VISUAL_DIR, f)) and os.path.splitext(f)[1].lower() in _VISUAL_EXTS],
                reverse=True,
            )
            if app.storage.user.get('visual_show_hidden', False):
                images = all_files
            else:
                images = [f for f in all_files if f not in hidden_set]
            
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
            with ui.element('div').classes('w-full h-full overflow-auto flex flex-col').style(_CHECKER_BG):
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
        if page_client._deleted:
            return
        _grid_open['value'] = False
        _view_state['current_image'] = path.lstrip('/')
        full_view = _gen_state.get('full_view_container')
        grid_view = _gen_state.get('grid_view_container')
        if not full_view or not grid_view: return
        
        grid_view.classes(add='hidden')
        full_view.classes(remove='hidden')
        full_view.clear()
        with full_view:
            _render_image_with_nav(path)

    def _update_selection_controls():
        selected_count = len(_selection_state['selected'])
        toggle_btn = _selection_state.get('toggle_btn')
        delete_btn = _selection_state.get('delete_btn')
        hide_btn = _selection_state.get('hide_btn')
        count_label = _selection_state.get('count_label')

        if toggle_btn:
            if _selection_state['active']:
                toggle_btn.props('icon=check_box color=primary')
            else:
                toggle_btn.props('icon=check_box_outline_blank color=white')

        if delete_btn:
            if _selection_state['active'] and selected_count:
                delete_btn.enable()
            else:
                delete_btn.disable()

        if hide_btn:
            if _selection_state['active'] and selected_count:
                hide_btn.enable()
            else:
                hide_btn.disable()

        if count_label:
            count_label.set_text(f'{selected_count} selected' if _selection_state['active'] else '')

    def _update_cell_selection(fpath: str):
        refs = _selection_state['cells'].get(fpath)
        if not refs:
            return
        overlay = refs.get('overlay')
        if not overlay:
            return
        if fpath in _selection_state['selected']:
            overlay.classes(remove='hidden')
        else:
            overlay.classes(add='hidden')

    def _toggle_selection_mode():
        _selection_state['active'] = not _selection_state['active']
        if not _selection_state['active']:
            selected = list(_selection_state['selected'])
            _selection_state['selected'].clear()
            for fpath in selected:
                _update_cell_selection(fpath)
        _update_selection_controls()

    def _toggle_image_selection(fpath: str):
        if fpath in _selection_state['selected']:
            _selection_state['selected'].remove(fpath)
        else:
            _selection_state['selected'].add(fpath)
        _update_cell_selection(fpath)
        _update_selection_controls()

    def _handle_grid_cell_click(full_src: str, fpath: str):
        if _selection_state['active']:
            _toggle_image_selection(fpath)
        else:
            show_image(full_src)

    def _register_selectable_cell(cell, fpath: str):
        with cell:
            with ui.element('div').classes(
                'hidden absolute inset-0 pointer-events-none'
            ).style(
                'background: rgba(124,58,237,0.28);'
                'box-shadow: inset 0 0 0 3px rgba(167,139,250,0.95);'
                'z-index: 8;'
            ) as overlay:
                ui.icon('check_circle', size='30px').classes(
                    'absolute top-2 right-2 text-purple-200 drop-shadow'
                )
        _selection_state['cells'][fpath] = {'cell': cell, 'overlay': overlay}
        _update_cell_selection(fpath)

    def _remove_image_files(fpath: str):
        if os.path.exists(fpath):
            os.remove(fpath)
        fname = os.path.basename(fpath)
        thumb_path = f"data/visual/thumbs/{fname}"
        if os.path.exists(thumb_path):
            os.remove(thumb_path)

    def _toggle_selected_images_hide():
        selected = list(_selection_state['selected'])
        if not selected:
            return
            
        hidden_images = app.storage.user.get('visual_hidden_images', [])
        if not isinstance(hidden_images, list):
            hidden_images = []
            
        any_visible = False
        for fpath in selected:
            fname = os.path.basename(fpath)
            if fname not in hidden_images:
                any_visible = True
                break
                
        if any_visible:
            for fpath in selected:
                fname = os.path.basename(fpath)
                if fname not in hidden_images:
                    hidden_images.append(fname)
            ui.notify(f"Hid {len(selected)} image(s).", type='info')
        else:
            for fpath in selected:
                fname = os.path.basename(fpath)
                if fname in hidden_images:
                    hidden_images.remove(fname)
            ui.notify(f"Unhid {len(selected)} image(s).", type='info')
            
        app.storage.user['visual_hidden_images'] = hidden_images
        _selection_state['selected'].clear()
        _selection_state['active'] = False
        _grid_element['ref'] = None
        show_history()
        _update_selection_controls()

    def _delete_selected_images():
        selected = list(_selection_state['selected'])
        if not selected:
            return

        deleted = 0
        try:
            for fpath in selected:
                _remove_image_files(fpath)
                deleted += 1

            last = app.storage.user.get('visual_last_image')
            if last and any(os.path.normpath(last) == os.path.normpath(path) for path in selected):
                app.storage.user['visual_last_image'] = None

            _selection_state['selected'].clear()
            _selection_state['active'] = False
            _grid_element['ref'] = None
            ui.notify(f'Deleted {deleted} image{"s" if deleted != 1 else ""}.', type='info')
            show_history()
        except Exception as exc:
            ui.notify(f'Could not delete selected images: {exc}', type='negative')
        finally:
            _update_selection_controls()

    def _new_visual_output_path(ext: str = '.png') -> str:
        import datetime

        os.makedirs(_VISUAL_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        candidate = os.path.join(_VISUAL_DIR, f'tess_{timestamp}{ext}').replace('\\', '/')
        idx = 2
        while os.path.exists(candidate):
            candidate = os.path.join(_VISUAL_DIR, f'tess_{timestamp}_{idx}{ext}').replace('\\', '/')
            idx += 1
        return candidate

    def _create_thumbnail(fpath: str):
        try:
            from PIL import Image
            fname = os.path.basename(fpath)
            thumb_dir = 'data/visual/thumbs'
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_path = os.path.join(thumb_dir, fname).replace('\\', '/')
            with Image.open(fpath) as img:
                img.thumbnail((256, 256))
                img.save(thumb_path)
        except Exception:
            pass

    def _image_text_metadata(fpath: str) -> dict:
        try:
            from PIL import Image
            with Image.open(fpath) as img:
                metadata = img.text if hasattr(img, 'text') else img.info
                return {
                    key: value for key, value in metadata.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
        except Exception:
            return {}

    def _tool_png_metadata(source_path: str, tool_meta: dict):
        import json
        from PIL.PngImagePlugin import PngInfo

        source_metadata = _image_text_metadata(source_path)
        metadata = PngInfo()

        for key, value in source_metadata.items():
            metadata.add_text(key, value)

        existing_tools = []
        if source_metadata.get('tools'):
            try:
                parsed_tools = json.loads(source_metadata['tools'])
                if isinstance(parsed_tools, list):
                    existing_tools = parsed_tools
            except Exception:
                existing_tools = []

        metadata.add_text('source_image', source_path.replace('\\', '/'))
        metadata.add_text('source_metadata', json.dumps(source_metadata, indent=2))
        metadata.add_text('tools', json.dumps([*existing_tools, tool_meta], indent=2))
        return metadata

    def _unload_remove_background_session():
        import gc

        _rembg_state['session'] = None
        _rembg_state['model'] = None
        gc.collect()

    def _remove_background_file(fpath: str, model_name: str) -> str:
        import datetime
        import io
        from rembg import new_session, remove
        from PIL import Image

        if _rembg_state['session'] is None or _rembg_state['model'] != model_name:
            _rembg_state['session'] = new_session(model_name)
            _rembg_state['model'] = model_name

        output_path = _new_visual_output_path()
        with open(fpath, 'rb') as input_file:
            input_bytes = input_file.read()
        output_bytes = remove(input_bytes, session=_rembg_state['session'])

        tool_meta = {
            'name': 'remove_background',
            'model': model_name,
            'source_image': fpath.replace('\\', '/'),
            'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
        }
        metadata = _tool_png_metadata(fpath, tool_meta)
        with Image.open(io.BytesIO(output_bytes)) as img:
            img.save(output_path, pnginfo=metadata)

        _create_thumbnail(output_path)
        return output_path

    def _tool_context_paths():
        if _grid_open['value']:
            return [path for path in _selection_state['selected'] if os.path.exists(path)]

        current = _view_state.get('current_image')
        if current and os.path.exists(current):
            return [current]
        return []

    async def _run_remove_background_from_context(paths=None, *, model_name=None, auto=False):
        targets = list(paths) if paths else _tool_context_paths()
        if not targets:
            _notify('Select images in grid view or open an image first.', type='warning')
            return []

        model_name = (model_name or app.storage.user.get('visual_remove_background_model', 'isnet-anime')).strip()
        if not model_name:
            _notify('Enter a rembg model name.', type='warning')
            return []

        _remember_remove_background_model(model_name)
        processed = []
        _set_remove_background_busy(True)
        try:
            for fpath in targets:
                output_path = await run.io_bound(_remove_background_file, fpath, model_name)
                processed.append(output_path)

            if processed:
                app.storage.user['visual_last_image'] = processed[-1]
                _grid_element['ref'] = None
                if _grid_open['value']:
                    _page_state['current_page'] = 1
                    _selection_state['selected'].clear()
                    _selection_state['active'] = False
                    show_history()
                else:
                    show_image(f'/{processed[-1]}')
                if not auto:
                    _notify(f'Removed background from {len(processed)} image{"s" if len(processed) != 1 else ""}.', type='positive')
        except ImportError:
            _notify('rembg is not installed. Run the project dependency sync, then try again.', type='negative')
        except Exception as exc:
            _notify(f'Could not remove background: {exc}', type='negative')
        finally:
            await run.io_bound(_unload_remove_background_session)
            _set_remove_background_busy(False)
            _update_selection_controls()

        return processed

    def prev_page():
        if _page_state['current_page'] > 1:
            _page_state['current_page'] -= 1
            _grid_element['ref'] = None
            show_history()

    def next_page():
        hidden_images = app.storage.user.get('visual_hidden_images', [])
        if not isinstance(hidden_images, list):
            hidden_images = []
        hidden_set = set(hidden_images)

        images = []
        if os.path.isdir(_VISUAL_DIR):
            all_files = [f for f in os.listdir(_VISUAL_DIR)
                         if os.path.isfile(os.path.join(_VISUAL_DIR, f)) and os.path.splitext(f)[1].lower() in _VISUAL_EXTS]
            if app.storage.user.get('visual_show_hidden', False):
                images = all_files
            else:
                images = [f for f in all_files if f not in hidden_set]
        total_pages = max(1, (len(images) + _page_state['page_size'] - 1) // _page_state['page_size'])
        if _page_state['current_page'] < total_pages:
            _page_state['current_page'] += 1
            _grid_element['ref'] = None
            show_history()

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

        hidden_images = app.storage.user.get('visual_hidden_images', [])
        if not isinstance(hidden_images, list):
            hidden_images = []
        hidden_set = set(hidden_images)

        images = []
        if os.path.isdir(_VISUAL_DIR):
            all_files = sorted(
                [f for f in os.listdir(_VISUAL_DIR)
                 if os.path.isfile(os.path.join(_VISUAL_DIR, f)) and os.path.splitext(f)[1].lower() in _VISUAL_EXTS],
                reverse=True,
            )
            if app.storage.user.get('visual_show_hidden', False):
                images = all_files
            else:
                images = [f for f in all_files if f not in hidden_set]

        total_images = len(images)
        page_size = _page_state['page_size']
        total_pages = max(1, (total_images + page_size - 1) // page_size)

        if _page_state['current_page'] > total_pages:
            _page_state['current_page'] = total_pages
        if _page_state['current_page'] < 1:
            _page_state['current_page'] = 1

        grid_view.clear()
        _selection_state['cells'] = {}
        _selection_state['toggle_btn'] = None
        _selection_state['delete_btn'] = None
        _selection_state['hide_btn'] = None
        _selection_state['count_label'] = None
        
        with grid_view:
            # Header bar
            with ui.row().classes('w-full items-center justify-between px-4 pt-3 pb-1').style(
                'flex-shrink: 0;'
            ):
                with ui.row().classes('items-center gap-1'):
                    prev_btn = ui.button(icon='chevron_left', on_click=prev_page).props('flat dense round').classes('text-white/60 hover:text-white')
                    page_label = ui.label(f"{_page_state['current_page']} / {total_pages}").classes('text-white/80 text-xs font-mono')
                    next_btn = ui.button(icon='chevron_right', on_click=next_page).props('flat dense round').classes('text-white/60 hover:text-white')
                    
                    if _page_state['current_page'] <= 1:
                        prev_btn.disable()
                    if _page_state['current_page'] >= total_pages:
                        next_btn.disable()

                with ui.row().classes('items-center justify-center gap-2'):
                    ui.label('Generation History').classes(
                        'text-white/60 text-sm font-semibold uppercase tracking-widest'
                    )
                    _selection_state['toggle_btn'] = ui.button(
                        icon='check_box_outline_blank',
                        on_click=_toggle_selection_mode,
                    ).props('flat dense round').style(
                        'width: 30px; height: 30px; min-height: unset;'
                        'color: rgba(255,255,255,0.55);'
                    ).tooltip('Select images')
                    ui.separator().props('vertical').classes('h-6 bg-white/20')
                    _selection_state['delete_btn'] = ui.button(
                        icon='delete',
                        on_click=_delete_selected_images,
                    ).props('flat dense round color=negative').style(
                        'width: 30px; height: 30px; min-height: unset;'
                    ).tooltip('Delete selected images')
                    _selection_state['hide_btn'] = ui.button(
                        icon='visibility_off',
                        on_click=_toggle_selected_images_hide,
                    ).props('flat dense round color=warning').style(
                        'width: 30px; height: 30px; min-height: unset;'
                    ).tooltip('Hide/Unhide selected images')
                    _selection_state['count_label'] = ui.label('').classes('text-white/40 text-xs font-mono')
                    _update_selection_controls()
                ui.button(icon='close', on_click=_restore_last).props('flat dense').classes(
                    'text-white/40 hover:text-white/80'
                ).tooltip('Back to current image')

            if not images:
                ui.label('No images found.').classes('text-white/30 m-auto')
                return

            # Slice images for the current page
            start_idx = (_page_state['current_page'] - 1) * page_size
            end_idx = start_idx + page_size
            visible_images = images[start_idx:end_idx]

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
                    os.makedirs("data/visual/thumbs", exist_ok=True)
                    for fname in visible_images:
                        fpath = f'{_VISUAL_DIR}/{fname}'
                        src = f'/{fpath}'
                        thumb_path = f'data/visual/thumbs/{fname}'
                        
                        if not os.path.exists(thumb_path):
                            thumb_src = src
                            asyncio.create_task(run.io_bound(_create_thumbnail, fpath))
                        else:
                            thumb_src = f'/{thumb_path}'
                                
                        _add_grid_cell(grid, thumb_src, src, fpath)

    # ── Helper: delete an image file and refresh the grid ───────────────────
    def _delete_image(fpath: str, cell_div=None):
        try:
            next_to_show = None
            if not _grid_open['value']:
                filename = os.path.basename(fpath)
                hidden_images = app.storage.user.get('visual_hidden_images', [])
                if not isinstance(hidden_images, list):
                    hidden_images = []
                hidden_set = set(hidden_images)
                if os.path.isdir(_VISUAL_DIR):
                    all_files = sorted(
                        [f for f in os.listdir(_VISUAL_DIR)
                         if os.path.isfile(os.path.join(_VISUAL_DIR, f)) and os.path.splitext(f)[1].lower() in _VISUAL_EXTS],
                        reverse=True,
                    )
                    if app.storage.user.get('visual_show_hidden', False):
                        images = all_files
                    else:
                        images = [f for f in all_files if f not in hidden_set]
                    try:
                        idx = images.index(filename)
                        if idx < len(images) - 1:
                            next_to_show = f"/{_VISUAL_DIR}/{images[idx + 1]}"
                        elif idx > 0:
                            next_to_show = f"/{_VISUAL_DIR}/{images[idx - 1]}"
                    except ValueError:
                        pass

            _remove_image_files(fpath)
            last = app.storage.user.get('visual_last_image')
            if last and os.path.normpath(last) == os.path.normpath(fpath):
                app.storage.user['visual_last_image'] = None
            _selection_state['selected'].discard(fpath)
            _selection_state['cells'].pop(fpath, None)
            _update_selection_controls()
                
            ui.notify('Image deleted.', type='info')
            
            if _grid_open['value']:
                _grid_element['ref'] = None
                show_history()
            elif not _grid_open['value']:
                if next_to_show:
                    app.storage.user['visual_last_image'] = next_to_show.lstrip('/')
                    show_image(next_to_show)
                else:
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

    def expand_prompt(prompt_str: str) -> list:
        import re
        import itertools
        pattern = re.compile(r'\[\[(.*?)\]\]')
        matches = list(pattern.finditer(prompt_str))
        if not matches:
            return [prompt_str]
        groups_options = []
        for match in matches:
            options = [opt.strip() for opt in match.group(1).split('|')]
            groups_options.append(options)
        combinations = list(itertools.product(*groups_options))
        expanded = []
        for combo in combinations:
            new_prompt = ""
            last_idx = 0
            for match, opt in zip(matches, combo):
                new_prompt += prompt_str[last_idx:match.start()] + opt
                last_idx = match.end()
            new_prompt += prompt_str[last_idx:]
            expanded.append(new_prompt)
        return expanded

    def _enqueue_job(raw_prompt_str: str, neg_prompt: str, steps_val: int, size_val: str, batch_count_val: int, cfg_scale_val: float = None, turbo_lora_val: float = None, input_image_val = None, denoising_strength_val: float = 1.0):
        try:
            w_str, h_str = size_val.split('x')
            w, h = int(w_str), int(h_str)
            pixels = w * h
            if pixels < 512 * 512 or pixels > 1536 * 1536:
                ui.notify(f"Resolution {w}x{h} ({pixels} pixels) is outside the supported range of 512² to 1536² pixels.", type='warning')
                return False
        except Exception as e:
            ui.notify(f"Invalid image resolution: {e}", type='warning')
            return False

        raw_prompts = [p.strip() for p in raw_prompt_str.split('///') if p.strip()]
        if not raw_prompts:
            return False
            
        expanded_prompts = []
        for p in raw_prompts:
            for ep in expand_prompt(p):
                expanded_prompts.extend([ep] * batch_count_val)
                
        if cfg_scale_val is None:
            cfg_scale_val = float(app.storage.user.get('visual_cfg_scale', 4.0))
        if turbo_lora_val is None:
            turbo_lora_val = float(app.storage.user.get('visual_turbo_lora_strength', 1.0)) if app.storage.user.get('visual_turbo_lora_enabled', False) else 0.0

        job = {
            'prompts': expanded_prompts,
            'negative_prompt': neg_prompt,
            'steps': steps_val,
            'image_size': size_val,
            'remove_background_auto': app.storage.user.get('visual_remove_background_auto', False),
            'remove_background_model': app.storage.user.get('visual_remove_background_model', 'isnet-anime'),
            'generate_previews': app.storage.user.get('visual_generate_previews', False),
            'cfg_scale': cfg_scale_val,
            'turbo_lora': turbo_lora_val,
            'input_image': input_image_val,
            'denoising_strength': denoising_strength_val,
        }
        _generation_queue.append(job)
        _update_queue_ui()
        if _gen_state['active']:
            _gen_state['global_total'] += len(expanded_prompts)
            _update_progress_labels()
        return True

    def _update_progress_labels():
        try:
            if page_client._deleted or not _gen_state['active']:
                return
                
            g_idx = _gen_state.get('global_idx', 1)
            g_tot = _gen_state.get('global_total', 1)
            
            if _gen_state.get('progress_sidebar_label'):
                _gen_state['progress_sidebar_label'].set_text(
                    f"Generating {g_idx} of {g_tot} (Preparing...)"
                )
        except Exception:
            pass

    def _update_queue_ui():
        pass

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
            
            prompt_val = params.get('prompt', '')
            neg_prompt = params.get('negative_prompt', '')
            steps_val = params.get('steps', 30)
            w = params.get('width', 1024)
            h = params.get('height', 1024)
            size_val = f"{w}x{h}"
            cfg_scale_val = params.get('cfg_scale', 4.0)
            turbo_lora_val = params.get('turbo_lora', 0.0)
            
            success = _enqueue_job(prompt_val, neg_prompt, steps_val, size_val, 1, cfg_scale_val=cfg_scale_val, turbo_lora_val=turbo_lora_val)
            if success:
                if _gen_state['active']:
                    ui.notify('Regeneration added to queue.', type='info')
                else:
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
            w = int(params.get('width', 1024))
            h = int(params.get('height', 1024))
            
            if isinstance(image_width.options, list):
                if w not in image_width.options:
                    image_width.options.append(w)
                    image_width.options.sort()
                    image_width.update()
            elif isinstance(image_width.options, dict):
                if w not in image_width.options:
                    image_width.options[w] = str(w)
                    image_width.update()
                    
            if isinstance(image_height.options, list):
                if h not in image_height.options:
                    image_height.options.append(h)
                    image_height.options.sort()
                    image_height.update()
            elif isinstance(image_height.options, dict):
                if h not in image_height.options:
                    image_height.options[h] = str(h)
                    image_height.update()
            
            image_width.value = w
            image_height.value = h
            
            cfg_val = params.get('cfg_scale', 4.0)
            cfg_scale_slider.value = cfg_val
            cfg_scale_label.set_text(f"{cfg_val:.1f}")
            
            turbo_val = params.get('turbo_lora', 0.0)
            if turbo_val > 0.0:
                turbo_checkbox.value = True
                turbo_strength_slider.value = turbo_val
                turbo_strength_label.set_text(f"{turbo_val:.2f}")
            else:
                turbo_checkbox.value = False
            
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
                'aspect-ratio: 1 / 1;'
                f'{_CHECKER_BG}'
                'transition: transform 0.15s ease, box-shadow 0.15s ease;'
            )
            cell.on('click', lambda s=full_src, p=fpath: _handle_grid_cell_click(s, p))
            with cell:
                ui.image(thumb_src).style(
                    'width:100%; height:100%; object-fit:cover; display:block;'
                )
                
                # Check if this image is hidden
                fname = os.path.basename(fpath)
                hidden_images = app.storage.user.get('visual_hidden_images', [])
                if not isinstance(hidden_images, list):
                    hidden_images = []
                if fname in hidden_images:
                    with ui.element('div').classes('absolute inset-0 bg-black/60 flex items-center justify-center pointer-events-none'):
                        ui.icon('visibility_off', size='24px').classes('text-white/60')
            _register_selectable_cell(cell, fpath)
            _add_delete_btn(cell, fpath)
            _add_regenerate_btn(cell, fpath)
            _add_info_btn(cell, fpath)

    def _restore_last():
        """Go back to the last generated image (or placeholder)."""
        _grid_open['value'] = False
        
        if _gen_state['active']:
            _inject_preview_canvas()
            return
            
        last = app.storage.user.get('visual_last_image')
        if last and os.path.exists(last):
            show_image(f'/{last}')
        else:
            show_placeholder()

    _gen_state['show_history'] = show_history
    _gen_state['show_image'] = show_image
    _gen_state['show_placeholder'] = show_placeholder
    _gen_state['inject_preview_canvas'] = _inject_preview_canvas
    _gen_state['update_progress_labels'] = _update_progress_labels

    if _grid_open['value']:
        show_history()
    elif _gen_state['active']:
        _inject_preview_canvas()
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
        itoi_btn = _gen_state.get('itoi_btn')
        if itoi_btn:
            itoi_btn.disable()
        if progress_sidebar:
            progress_sidebar.classes(remove='hidden')
            g_idx = _gen_state.get('global_idx', 1)
            g_tot = _gen_state.get('global_total', 1)
            pct = _gen_state.get('pct', 0)
            progress_sidebar_label.set_text(f"Generating {g_idx} of {g_tot}")
            progress_sidebar_bar.set_value(pct / 100)

    # ── Generate handler ─────────────────────────────────────────────────────
    async def on_generate():
        if _gen_state.get('active'):
            return
            
        user_storage = app.storage.user
        def safe_notify(msg, **kwargs):
            try:
                active_client = _gen_state.get('client')
                if active_client and not active_client._deleted:
                    active_client.notify(msg, **kwargs)
            except Exception:
                pass

        _gen_state['active'] = True
        _gen_state['cancel'] = False
        
        # Show sidebar progress UI
        if _gen_state.get('progress_sidebar'):
            _gen_state['progress_sidebar'].classes(remove='hidden')
        if _gen_state.get('progress_sidebar_bar'):
            _gen_state['progress_sidebar_bar'].set_value(0)
            
        gen_btn = _gen_state.get('generate_btn')
        if gen_btn:
            gen_btn.props('color=red icon=stop')
            gen_btn.set_text('Stop')
            gen_btn.classes(remove='from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600', add='from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600')
        
        i_btn = _gen_state.get('itoi_btn')
        if i_btn:
            i_btn.disable()
        
        _page_state['current_page'] = 1
        if _grid_open['value']:
            _grid_element['ref'] = None
            if _gen_state.get('show_history'):
                _gen_state['show_history']()
        else:
            _grid_element['ref'] = None
        
        _gen_state['global_idx'] = 0
        _gen_state['global_total'] = sum(len(job['prompts']) for job in _generation_queue)
        
        # Free up VRAM by unloading any active LLMs
        try:
            from utils.llm_client import client as llm_client
            await llm_client.unload_all_models()
        except Exception as e:
            print(f"Failed to unload LLMs before visual generation: {e}")

        loop = asyncio.get_event_loop()

        def on_progress(step: int, total: int, preview_path: str = None):
            if _gen_state.get('cancel'):
                return "CANCEL"
            if total == 0:
                return
            pct = min(round(step / total * 100), 100)
            _gen_state['pct'] = pct
            
            def _update():
                try:
                    active_client = _gen_state.get('client')
                    if not active_client or active_client._deleted:
                        return
                    if _gen_state.get('progress_sidebar_bar'):
                        _gen_state['progress_sidebar_bar'].set_value(pct / 100)
                    if _gen_state.get('progress_sidebar_label'):
                        g_idx = _gen_state.get('global_idx', 1)
                        g_tot = _gen_state.get('global_total', 1)
                        _gen_state['progress_sidebar_label'].set_text(
                            f"Generating {g_idx} of {g_tot} (Step {step}/{total})"
                        )
                    if preview_path and os.path.exists(preview_path):
                        import time
                        ts = int(time.time() * 1000)
                        if _gen_state.get('preview_image'):
                            _gen_state['preview_image'].classes(remove='hidden')
                            _gen_state['preview_image'].props(f'src="/{preview_path}?t={ts}"')
                except Exception:
                    pass
            loop.call_soon_threadsafe(_update)

        try:
            while _generation_queue and not _gen_state.get('cancel'):
                job = _generation_queue.pop(0)
                _update_queue_ui()
                
                raw_prompts = job['prompts']
                total_prompts = len(raw_prompts)
                
                _page_state['current_page'] = 1
                if _grid_open['value']:
                    _grid_element['ref'] = None
                    if _gen_state.get('show_history'):
                        _gen_state['show_history']()
                else:
                    _grid_element['ref'] = None
                _gen_state['total'] = total_prompts
                _gen_state['pct'] = 0
                
                for idx, current_p in enumerate(raw_prompts):
                    if _gen_state.get('cancel'):
                        break
                        
                    _gen_state['global_idx'] += 1
                    _gen_state['idx'] = idx
                    _gen_state['batch_prefix'] = f"[{_gen_state['global_idx']}/{_gen_state['global_total']}] "
                    _gen_state['pct'] = 0
                    
                    if not _grid_open['value'] and _gen_state.get('inject_preview_canvas'):
                        _gen_state['inject_preview_canvas']()
                        
                    if _gen_state.get('update_progress_labels'):
                        _gen_state['update_progress_labels']()

                    try:
                        w_str, h_str = job['image_size'].split('x')
                        output_path = await run.io_bound(
                            generate_image_task,
                            current_p,
                            job['negative_prompt'],
                            job['steps'],
                            int(w_str),
                            int(h_str),
                            on_progress,
                            unload_after=False,
                            generate_previews=job['generate_previews'],
                            cfg_scale=job['cfg_scale'],
                            turbo_lora=job['turbo_lora'],
                            input_image=job.get('input_image'),
                            denoising_strength=job.get('denoising_strength', 1.0)
                        )
                        
                        if not output_path:
                            break

                        if job['remove_background_auto']:
                            safe_notify('Removing background...', type='info', pos='bottom-right', timeout=1500)
                            try:
                                model_name = job['remove_background_model']
                                output_path = await run.io_bound(_remove_background_file, output_path, model_name)
                            except Exception as tool_exc:
                                safe_notify(f'Background removal failed: {tool_exc}', type='negative')
                            finally:
                                await run.io_bound(_unload_remove_background_session)

                        user_storage['visual_last_image'] = output_path
                        
                        active_client = _gen_state.get('client')
                        _gen_state['preview_image'] = None
                        
                        if active_client and not active_client._deleted:
                            if _grid_open['value'] and _gen_state.get('show_history'):
                                _grid_element['ref'] = None
                                _gen_state['show_history']()
                            elif not _view_state['current_image'] and _gen_state.get('show_image'):
                                _gen_state['show_image'](f'/{output_path}')

                        if total_prompts == 1:
                            safe_notify('Image generated successfully!', type='positive')
                        else:
                            safe_notify(f'Generated {idx+1}/{total_prompts}', type='positive', pos='bottom-right', timeout=2000)

                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        _gen_state['preview_image'] = None
                        safe_notify(f'Failed to generate image {idx+1}: {str(e)}', type='negative')
        
        finally:
            try:
                from services.visual_service import unload_pipeline
                await run.io_bound(unload_pipeline)
            except Exception as e:
                print(f"Failed to unload visual pipeline in finally block: {e}")

            is_canceled = _gen_state.get('cancel', False)
            _gen_state['active'] = False
            _gen_state['cancel'] = False
            _gen_state['preview_image'] = None

            active_client = _gen_state.get('client')
            if active_client and not active_client._deleted:
                # Hide sidebar progress UI
                if _gen_state.get('progress_sidebar'):
                    _gen_state['progress_sidebar'].classes(add='hidden')

                gen_btn = _gen_state.get('generate_btn')
                if gen_btn:
                    gen_btn.enable()
                    gen_btn.props('color=primary icon=brush')
                    gen_btn.set_text('Generate')
                    gen_btn.classes(add='from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600', remove='from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600')
                
                i_btn = _gen_state.get('itoi_btn')
                if i_btn:
                    i_btn.enable()
                
                _update_queue_ui()

                if not _grid_open['value'] and not _view_state['current_image']:
                    last = user_storage.get('visual_last_image')
                    if last and os.path.exists(last):
                        if _gen_state.get('show_image'):
                            _gen_state['show_image'](f'/{last}')
                    else:
                        if _gen_state.get('show_placeholder'):
                            _gen_state['show_placeholder']()
                
                if is_canceled:
                    safe_notify('Generation stopped.', type='warning')
                elif total_prompts > 1:
                    safe_notify(f'Batch processing of {total_prompts} prompts complete.', type='info')

    async def on_generate_click():
        if _gen_state.get('active'):
            _gen_state['cancel'] = True
            _generation_queue.clear()
            _update_queue_ui()
            gen_btn = _gen_state.get('generate_btn')
            if gen_btn:
                gen_btn.set_text('Stopping...')
                gen_btn.disable()
        else:
            raw_prompt_str = prompt.value
            neg_prompt = negative_prompt.value
            steps_val = int(steps.value)
            size_val = f"{image_width.value}x{image_height.value}"
            batch_count_val = int(batch_count.value)
            
            cfg_scale_val = float(app.storage.user.get('visual_cfg_scale', 4.0))
            turbo_lora_val = float(app.storage.user.get('visual_turbo_lora_strength', 1.0)) if app.storage.user.get('visual_turbo_lora_enabled', False) else 0.0
            
            success = _enqueue_job(
                raw_prompt_str, 
                neg_prompt, 
                steps_val, 
                size_val, 
                batch_count_val,
                cfg_scale_val=cfg_scale_val,
                turbo_lora_val=turbo_lora_val
            )
            if not success:
                ui.notify('Please enter a positive prompt', type='warning')
                return
            await on_generate()

    async def on_queue_click():
        raw_prompt_str = prompt.value
        neg_prompt = negative_prompt.value
        steps_val = int(steps.value)
        size_val = f"{image_width.value}x{image_height.value}"
        batch_count_val = int(batch_count.value)
        
        cfg_scale_val = float(app.storage.user.get('visual_cfg_scale', 4.0))
        turbo_lora_val = float(app.storage.user.get('visual_turbo_lora_strength', 1.0)) if app.storage.user.get('visual_turbo_lora_enabled', False) else 0.0
        
        success = _enqueue_job(
            raw_prompt_str, 
            neg_prompt, 
            steps_val, 
            size_val, 
            batch_count_val,
            cfg_scale_val=cfg_scale_val,
            turbo_lora_val=turbo_lora_val
        )
        if not success:
            ui.notify('Please enter a positive prompt', type='warning')
            return
            
        ui.notify('Added to queue.', type='info')
        if not _gen_state['active']:
            await on_generate()

    async def on_itoi_click():
        if _gen_state.get('active'):
            return
            
        try:
            input_paths = _tool_context_paths()
            if not input_paths:
                ui.notify('Please select an image in the history grid or open an image first to use as the input image.', type='warning')
                return
                
            raw_prompt_str = prompt.value
            if not raw_prompt_str or not raw_prompt_str.strip():
                ui.notify('Please enter a positive prompt', type='warning')
                return
                
            neg_prompt = negative_prompt.value
            steps_val = int(steps.value)
            size_val = f"{image_width.value}x{image_height.value}"
            batch_count_val = int(batch_count.value)
            
            cfg_scale_val = float(app.storage.user.get('visual_cfg_scale', 4.0))
            turbo_lora_val = float(app.storage.user.get('visual_turbo_lora_strength', 1.0)) if app.storage.user.get('visual_turbo_lora_enabled', False) else 0.0
            denoising_strength_val = float(app.storage.user.get('visual_denoising_strength', 0.6))
            
            # Enqueue a job for each selected input image
            for path in input_paths:
                _enqueue_job(
                    raw_prompt_str,
                    neg_prompt,
                    steps_val,
                    size_val,
                    batch_count_val,
                    cfg_scale_val=cfg_scale_val,
                    turbo_lora_val=turbo_lora_val,
                    input_image_val=path,
                    denoising_strength_val=denoising_strength_val
                )
                
            ui.notify(f'Added {len(input_paths)} image-to-image job(s) to queue.', type='info')
            await on_generate()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"Error in on_itoi_click: {e}\n{tb}")
            ui.notify(f"Error starting i2i: {e}", type='negative')
 
    if generate_btn:
        generate_btn.on('click', on_generate_click)
    if queue_btn:
        queue_btn.on('click', on_queue_click)
    if itoi_btn:
        itoi_btn.on('click', on_itoi_click)
    _update_queue_ui()
