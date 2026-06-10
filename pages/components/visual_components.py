import os
from typing import TypedDict, Callable, Any
from nicegui import ui, app
from services.visual_service import (
    _VISUAL_EXTS,
    _VISUAL_DIR,
    get_hidden_images
)

class VisualActionCallbacks(TypedDict):
    delete: Callable[[str, Any], None]
    regenerate: Callable[[str], Any]
    info: Callable[[str], Any]
    download: Callable[[str], Any]
    edit: Callable[[str], Any]
    hide: Callable[[str], Any]

def add_image_context_menu(container, fpath: str, callbacks: VisualActionCallbacks):
    with container:
        with ui.context_menu():
            ui.menu_item('Download Image', on_click=lambda: callbacks['download'](fpath))
            ui.menu_item('Delete', on_click=lambda: callbacks['delete'](fpath, container))
            ui.menu_item('Regenerate', on_click=lambda: callbacks['regenerate'](fpath))
            ui.menu_item('Hide/Unhide Image(s)', on_click=lambda: callbacks['hide'](fpath))
            ui.menu_item('Load Parameters', on_click=lambda: callbacks['info'](fpath))
            ui.menu_item('Edit in Photopea', on_click=lambda: callbacks['edit'](fpath))

def render_checkerboard_image(path: str):
    viewport = ui.element('div').classes(
        'checkerboard-bg w-full h-full min-h-0 overflow-hidden flex items-center justify-center'
    )
    with viewport:
        image = ui.element('img').props(f'src="{path}"').classes(
            'max-w-full max-h-full w-auto h-auto object-contain rounded-lg shadow-xl transition-all duration-300'
        )
    return viewport, image

def render_image_with_nav(path: str, show_history_cb, show_image_cb, callbacks: VisualActionCallbacks):
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

    with ui.element('div').classes('w-full h-full min-h-0 relative group') as img_div:
        viewport, img = render_checkerboard_image(path)
        
        fpath = path.lstrip('/')
        add_image_context_menu(img_div, fpath, callbacks)
        
        zoom_state = {'fit': True}
        
        with ui.row().classes(
            'absolute top-1 left-1/2 -translate-x-1/2 flex items-center gap-2 '
            'opacity-0 group-hover:opacity-100 transition-opacity z-10'
        ):
            def toggle_zoom():
                if zoom_state['fit']:
                    viewport.classes(remove='overflow-hidden items-center justify-center', add='overflow-auto items-start justify-start')
                    img.classes(remove='max-w-full max-h-full', add='max-w-none max-h-none')
                    zoom_btn.props('icon=zoom_out')
                    zoom_state['fit'] = False
                else:
                    viewport.classes(remove='overflow-auto items-start justify-start', add='overflow-hidden items-center justify-center')
                    img.classes(remove='max-w-none max-h-none', add='max-w-full max-h-full')
                    zoom_btn.props('icon=zoom_in')
                    zoom_state['fit'] = True
                    
            zoom_btn = ui.button(icon='zoom_in', on_click=toggle_zoom).props('flat dense round').classes(
                'visual-action-btn text-xs'
            ).tooltip('Toggle Zoom')
            
            ui.button(icon='grid_view', on_click=show_history_cb).props('flat dense round').classes(
                'visual-action-btn text-xs'
            ).tooltip('Visual History Grid')
        
        if prev_img:
            ui.button(icon='chevron_left', on_click=lambda p=prev_img: show_image_cb(p)).props('round flat size=lg').classes(
                'absolute left-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white hover:bg-black/80 z-10'
            )
        if next_img:
            ui.button(icon='chevron_right', on_click=lambda n=next_img: show_image_cb(n)).props('round flat size=lg').classes(
                'absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white hover:bg-black/80 z-10'
            )

def add_grid_cell(grid, thumb_src: str, full_src: str, fpath: str, is_hidden: bool, click_cb, register_cell_cb, callbacks: VisualActionCallbacks):
    with grid:
        cell = ui.element('div').classes('group visual-grid-cell checkerboard-bg')
        cell.on('click', lambda: click_cb(full_src, fpath))
        with cell:
            ui.image(thumb_src).classes('w-full h-full object-cover block')
            
            if is_hidden:
                with ui.element('div').classes('absolute inset-0 bg-black/60 flex items-center justify-center pointer-events-none'):
                    ui.icon('visibility_off', size='24px').classes('text-white/60')
        register_cell_cb(cell, fpath)
        add_image_context_menu(cell, fpath, callbacks)
