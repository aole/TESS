import os
import inspect
from typing import TypedDict, Callable, Any
from PIL import Image
from nicegui import ui, app
from services.visual_service import (
    _VISUAL_EXTS,
    _VISUAL_DIR,
    get_hidden_images
)
from core.db import visual_images_repo

class VisualActionCallbacks(TypedDict):
    delete: Callable[[str, Any], None]
    regenerate: Callable[[str], Any]
    info: Callable[[str], Any]
    download: Callable[[str], Any]
    edit: Callable[[str], Any]
    hide: Callable[[str], Any]
    generate_prompt: Callable[[str], Any]
    send_to_chat: Callable[[str], Any]

def _menu_action(callback: Callable, *args):
    async def handler(*_):
        result = callback(*args)
        if inspect.isawaitable(result):
            await result
    return handler

def _context_menu_item(label: str, icon: str, on_click: Callable, icon_class: str = 'text-indigo-4'):
    with ui.menu_item(on_click=on_click):
        with ui.item_section().props('avatar'):
            ui.icon(icon).classes(icon_class)
        with ui.item_section():
            ui.label(label)

def add_image_context_menu(container, fpath: str, callbacks: VisualActionCallbacks):
    with container:
        with ui.context_menu():
            _context_menu_item('Download Image', 'download', _menu_action(callbacks['download'], fpath), 'text-blue-4')
            _context_menu_item('Delete', 'delete', _menu_action(callbacks['delete'], fpath, container), 'text-red-4')
            _context_menu_item('Regenerate', 'refresh', _menu_action(callbacks['regenerate'], fpath), 'text-purple-4')
            _context_menu_item('Hide/Unhide Image(s)', 'visibility_off', _menu_action(callbacks['hide'], fpath), 'text-amber-4')
            _context_menu_item('Load Parameters', 'tune', _menu_action(callbacks['info'], fpath), 'text-cyan-4')
            _context_menu_item('Generate Prompt with AI', 'auto_awesome', _menu_action(callbacks['generate_prompt'], fpath), 'text-indigo-4')
            _context_menu_item('Send to Chat', 'chat', _menu_action(callbacks['send_to_chat'], fpath), 'text-green-4')
            _context_menu_item('Edit in Photopea', 'edit', _menu_action(callbacks['edit'], fpath), 'text-pink-4')

def render_checkerboard_image(path: str):
    viewport = ui.element('div').classes(
        'checkerboard-bg w-full h-full min-h-0 overflow-hidden flex items-center justify-center'
    )
    with viewport:
        image = ui.element('img').props(f'src="{path}"').classes(
            'max-w-full max-h-full w-auto h-auto object-contain rounded-lg shadow-xl transition-all duration-300'
        )
    return viewport, image

def get_image_dimensions(path: str) -> str:
    try:
        with Image.open(path.lstrip('/')) as image:
            width, height = image.size
        return f'{width}x{height}'
    except Exception:
        return ''

def render_image_with_nav(path: str, show_history_cb, show_image_cb, callbacks: VisualActionCallbacks):
    images = visual_images_repo.list_images(include_hidden=app.storage.user.get('visual_show_hidden', False))
    paths = [row['path'] for row in images]
    filename = os.path.basename(path)
    dimensions = get_image_dimensions(path)
    prev_img = None
    next_img = None
    
    try:
        idx = paths.index(path.lstrip('/'))
        if idx > 0:
            prev_img = f"/{paths[idx - 1]}"
        if idx < len(paths) - 1:
            next_img = f"/{paths[idx + 1]}"
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

        ui.label(filename).classes(
            'absolute bottom-2 left-2 max-w-[60%] truncate rounded bg-black/70 px-2 py-1 '
            'text-xs text-white/80 opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none'
        )
        if dimensions:
            ui.label(dimensions).classes(
                'absolute bottom-2 right-2 rounded bg-black/70 px-2 py-1 '
                'text-xs font-mono text-white/80 opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none'
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
