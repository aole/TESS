import os
from nicegui import ui, app
from services.visual_service import (
    _VISUAL_EXTS,
    _VISUAL_DIR,
    get_hidden_images
)

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

def add_delete_button(cell_div, fpath: str, delete_cb):
    with cell_div:
        btn = ui.button(icon='delete').props('flat dense round').style(
            'position: absolute; bottom: 4px; left: 4px;'
            'width: 26px; height: 26px; min-height: unset;'
            'background: rgba(0,0,0,0.75);'
            'color: white;'
            'transition: opacity 0.15s ease;'
            'z-index: 10;'
        ).classes('text-xs opacity-0 group-hover:opacity-100')
        btn.on('click.stop', lambda: delete_cb(fpath, cell_div))

def add_edit_button(cell_div, fpath: str):
    with cell_div:
        btn = ui.button(icon='edit').props('flat dense round').style(
            'position: absolute; bottom: 4px; right: 4px;'
            'width: 26px; height: 26px; min-height: unset;'
            'background: rgba(0,0,0,0.75);'
            'color: white;'
            'transition: opacity 0.15s ease;'
            'z-index: 10;'
        ).classes('text-xs opacity-0 group-hover:opacity-100').tooltip('Edit in Photopea')
        btn.on('click.stop', lambda: ui.navigate.to(f'/edit?img={fpath}'))

def add_regenerate_button(cell_div, fpath: str, regenerate_cb):
    with cell_div:
        btn = ui.button(icon='refresh').props('flat dense round').style(
            'position: absolute; top: 4px; left: 4px;'
            'width: 26px; height: 26px; min-height: unset;'
            'background: rgba(0,0,0,0.75);'
            'color: white;'
            'transition: opacity 0.15s ease;'
            'z-index: 10;'
        ).classes('text-xs opacity-0 group-hover:opacity-100').tooltip('Regenerate')
        btn.on('click.stop', lambda: regenerate_cb(fpath))

def add_info_button(cell_div, fpath: str, info_cb):
    with cell_div:
        btn = ui.button(icon='info').props('flat dense round').style(
            'position: absolute; top: 4px; right: 4px;'
            'width: 26px; height: 26px; min-height: unset;'
            'background: rgba(0,0,0,0.75);'
            'color: white;'
            'transition: opacity 0.15s ease;'
            'z-index: 10;'
        ).classes('text-xs opacity-0 group-hover:opacity-100').tooltip('Load Parameters')
        btn.on('click.stop', lambda: info_cb(fpath))

def add_hover_buttons(cell_div, fpath: str, callbacks: dict):
    add_delete_button(cell_div, fpath, callbacks['delete'])
    add_regenerate_button(cell_div, fpath, callbacks['regenerate'])
    add_info_button(cell_div, fpath, callbacks['info'])
    add_edit_button(cell_div, fpath)

def render_checkerboard_image(path: str):
    with ui.element('div').classes('w-full h-full overflow-auto flex flex-col').style(_CHECKER_BG):
        return ui.element('img').props(f'src="{path}"').classes(
            'm-auto w-full h-full object-contain rounded-lg shadow-xl transition-all duration-300'
        )

def render_image_with_nav(path: str, show_history_cb, show_image_cb, callbacks: dict):
    hidden_images = get_hidden_images()
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
        img = render_checkerboard_image(path)
        
        fpath = path.lstrip('/')
        add_hover_buttons(img_div, fpath, callbacks)
        
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
            
            ui.button(icon='grid_view', on_click=show_history_cb).props('flat dense round').style(
                'width: 26px; height: 26px; min-height: unset;'
                'background: rgba(0,0,0,0.75); color: white;'
            ).classes('text-xs').tooltip('Visual History Grid')
        
        if prev_img:
            ui.button(icon='chevron_left', on_click=lambda p=prev_img: show_image_cb(p)).props('round flat size=lg').classes(
                'absolute left-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white hover:bg-black/80 z-10'
            )
        if next_img:
            ui.button(icon='chevron_right', on_click=lambda n=next_img: show_image_cb(n)).props('round flat size=lg').classes(
                'absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white hover:bg-black/80 z-10'
            )

def add_grid_cell(grid, thumb_src: str, full_src: str, fpath: str, is_hidden: bool, click_cb, register_cell_cb, callbacks: dict):
    with grid:
        cell = ui.element('div').classes('group').style(
            'position: relative; overflow: hidden; cursor: pointer;'
            'aspect-ratio: 1 / 1;'
            f'{_CHECKER_BG}'
            'transition: transform 0.15s ease, box-shadow 0.15s ease;'
        )
        cell.on('click', lambda: click_cb(full_src, fpath))
        with cell:
            ui.image(thumb_src).style(
                'width:100%; height:100%; object-fit:cover; display:block;'
            )
            
            if is_hidden:
                with ui.element('div').classes('absolute inset-0 bg-black/60 flex items-center justify-center pointer-events-none'):
                    ui.icon('visibility_off', size='24px').classes('text-white/60')
        register_cell_cb(cell, fpath)
        add_hover_buttons(cell, fpath, callbacks)
