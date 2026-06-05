import os
import torch
from core.generate_image import generate_anima_image, get_pipeline, unload_pipeline, flush

def generate_image_task(
    prompt: str,
    negative_prompt: str,
    steps: int = 30,
    width: int = 1024,
    height: int = 1024,
    progress_callback = None,
    unload_after: bool = True,
    cfg_scale: float = 4.0,
    turbo_lora: float = 0.0,
    input_image = None,
    denoising_strength: float = 1.0,
) -> str:
    """
    NiceGUI-specific wrapper that generates an image using Anima and handles
    intermediate preview files and thumbnail creation.
    """
    # 1. Setup output paths
    import datetime
    os.makedirs("data/visual/images", exist_ok=True)
    os.makedirs("data/visual/thumbs", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"tess_{timestamp}.png"
    output_path = f"data/visual/images/{fname}"

    # 2. Generate the image
    res_path = generate_anima_image(
        prompt=prompt,
        output_path=output_path,
        negative_prompt=negative_prompt,
        steps=steps,
        width=width,
        height=height,
        progress_callback=progress_callback,
        unload_after=unload_after,
        cfg_scale=cfg_scale,
        turbo_lora=turbo_lora,
        input_image=input_image,
        denoising_strength=denoising_strength,
    )

    if not res_path:
        return None

    # 5. Generate and save thumbnail
    try:
        from PIL import Image
        with Image.open(res_path) as img:
            thumb = img.copy()
            thumb.thumbnail((256, 256))
            thumb_path = os.path.join("data/visual/thumbs", fname)
            thumb.save(thumb_path)
    except Exception as e:
        print(f"Failed to generate thumbnail: {e}")

    return res_path


_VISUAL_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
_VISUAL_DIR  = 'data/visual/images'

_rembg_state = {
    'session': None,
    'model': None,
}

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

def new_visual_output_path(ext: str = '.png') -> str:
    import datetime

    os.makedirs(_VISUAL_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    candidate = os.path.join(_VISUAL_DIR, f'tess_{timestamp}{ext}').replace('\\', '/')
    idx = 2
    while os.path.exists(candidate):
        candidate = os.path.join(_VISUAL_DIR, f'tess_{timestamp}_{idx}{ext}').replace('\\', '/')
        idx += 1
    return candidate

def create_thumbnail(fpath: str):
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

def remove_image_files(fpath: str):
    if os.path.exists(fpath):
        os.remove(fpath)
    fname = os.path.basename(fpath)
    thumb_path = f"data/visual/thumbs/{fname}"
    if os.path.exists(thumb_path):
        os.remove(thumb_path)

def image_text_metadata(fpath: str) -> dict:
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

def tool_png_metadata(source_path: str, tool_meta: dict):
    import json
    from PIL.PngImagePlugin import PngInfo

    source_metadata = image_text_metadata(source_path)
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

def unload_remove_background_session():
    import gc

    _rembg_state['session'] = None
    _rembg_state['model'] = None
    gc.collect()

def remove_background_file(fpath: str, model_name: str) -> str:
    import datetime
    import io
    from rembg import new_session, remove
    from PIL import Image

    if _rembg_state['session'] is None or _rembg_state['model'] != model_name:
        _rembg_state['session'] = new_session(model_name)
        _rembg_state['model'] = model_name

    output_path = new_visual_output_path()
    with open(fpath, 'rb') as input_file:
        input_bytes = input_file.read()
    output_bytes = remove(input_bytes, session=_rembg_state['session'])

    tool_meta = {
        'name': 'remove_background',
        'model': model_name,
        'source_image': fpath.replace('\\', '/'),
        'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    metadata = tool_png_metadata(fpath, tool_meta)
    with Image.open(io.BytesIO(output_bytes)) as img:
        img.save(output_path, pnginfo=metadata)

    create_thumbnail(output_path)
    return output_path


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
    'show_history': None,
    'show_image': None,
    'show_placeholder': None,
    'update_progress_labels': None,
}

_generation_queue = []


