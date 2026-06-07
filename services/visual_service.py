import os
import asyncio
import datetime
import json
import re
import gc
import itertools
import io
from PIL import Image
from nicegui import ui, run, app
from core.generate_image import generate_anima_image, unload_pipeline
from utils.llm_client import client as llm_client
from core.modify_image import modify_image as core_modify_image, unload_session as unload_modify_image_session

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

# State is managed in core/modify_image.py

def expand_prompt(prompt_str: str) -> list:
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

def unload_remove_background_session():
    unload_modify_image_session()

def remove_background_file(fpath: str, model_name: str) -> str:
    output_path = new_visual_output_path()
    core_modify_image(
        input_path=fpath,
        output_path=output_path,
        operation="remove_background",
        model_name=model_name,
        unload_after=False,
    )
    create_thumbnail(output_path)
    return output_path



_grid_open = {'value': True}
_grid_element = {'ref': None}
_page_state = {
    'current_page': 1,
    'page_size': 12,
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

_settings_ui = {}

def _update_queue_ui():
    pass

def _update_progress_labels():
    try:
        active_client = _gen_state.get('client')
        if not active_client or active_client._deleted or not _gen_state['active']:
            return
            
        g_idx = _gen_state.get('global_idx', 1)
        g_tot = _gen_state.get('global_total', 1)
        
        if _gen_state.get('progress_sidebar_label'):
            _gen_state['progress_sidebar_label'].set_text(
                f"Generating {g_idx} of {g_tot} (Preparing...)"
            )
    except Exception:
        pass

def _enqueue_job(raw_prompt_str: str, neg_prompt: str, steps_val: int, size_val: str, batch_count_val: int, cfg_scale_val=None, turbo_lora_val=None, input_image_val=None, denoising_strength_val: float = 1.0):
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

async def _regenerate_image(fpath: str):
    try:
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

_HIDDEN_IMAGES_FILE = 'data/visual/hidden_images.json'

def get_hidden_images() -> list:
    if not os.path.exists(_HIDDEN_IMAGES_FILE):
        return []
    try:
        with open(_HIDDEN_IMAGES_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []

def set_hidden_images(hidden_list: list):
    try:
        os.makedirs(os.path.dirname(_HIDDEN_IMAGES_FILE), exist_ok=True)
        with open(_HIDDEN_IMAGES_FILE, 'w') as f:
            json.dump(hidden_list, f, indent=4)
    except Exception as e:
        print(f"Error saving hidden images: {e}")

def _update_select_options(select_el, val):
    if isinstance(select_el.options, list):
        seen = set()
        cleaned = []
        for x in select_el.options + [val]:
            parsed = int(x) if str(x).isdigit() else x
            if parsed not in seen:
                seen.add(parsed)
                cleaned.append(parsed)
        try:
            cleaned.sort(key=int)
        except Exception:
            try:
                cleaned.sort()
            except Exception:
                pass
        select_el.options = cleaned
        select_el.update()
    elif isinstance(select_el.options, dict):
        if val not in select_el.options:
            select_el.options[val] = str(val)
            select_el.update()

def _load_metadata(fpath: str):
    try:
        w = None
        h = None
        params = {}
        has_params = False

        with Image.open(fpath) as img:
            w, h = img.size
            metadata = img.text if hasattr(img, 'text') else img.info
            if metadata:
                params_str = metadata.get('parameters')
                if params_str:
                    try:
                        params = json.loads(params_str)
                        has_params = True
                    except Exception:
                        pass
        
        if has_params:
            _settings_ui['prompt'].value = params.get('prompt', '')
            _settings_ui['negative_prompt'].value = params.get('negative_prompt', '')
            _settings_ui['steps'].value = params.get('steps', 30)
            w = int(params.get('width', w))
            h = int(params.get('height', h))
            
            cfg_val = params.get('cfg_scale', 4.0)
            _settings_ui['cfg_scale_slider'].value = cfg_val
            _settings_ui['cfg_scale_label'].set_text(f"{cfg_val:.1f}")
            
            turbo_val = params.get('turbo_lora', 0.0)
            if turbo_val > 0.0:
                _settings_ui['turbo_checkbox'].value = True
                _settings_ui['turbo_strength_slider'].value = turbo_val
                _settings_ui['turbo_strength_label'].set_text(f"{turbo_val:.2f}")
            else:
                _settings_ui['turbo_checkbox'].value = False
        else:
            ui.notify('No generation metadata found, loaded image dimensions instead.', type='warning')

        if w is not None and h is not None:
            image_width = _settings_ui['image_width']
            image_height = _settings_ui['image_height']
            
            _update_select_options(image_width, w)
            _update_select_options(image_height, h)
            
            image_width.value = w
            image_height.value = h

        if has_params:
            ui.notify('Parameters loaded from metadata.', type='info')
        
    except Exception as e:
        ui.notify(f"Could not read metadata: {e}", type='negative')

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
        await llm_client.unload_all_models()
    except Exception as e:
        print(f"Failed to unload LLMs before visual generation: {e}")

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
                            output_path = await run.io_bound(remove_background_file, output_path, model_name)
                        except Exception as tool_exc:
                            safe_notify(f'Background removal failed: {tool_exc}', type='negative')
                        finally:
                            await run.io_bound(unload_remove_background_session)

                    user_storage['visual_last_image'] = output_path
                    
                    active_client = _gen_state.get('client')
                    
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
                    safe_notify(f'Failed to generate image {idx+1}: {str(e)}', type='negative')
    
    finally:
        try:
            await run.io_bound(unload_pipeline)
        except Exception as e:
            print(f"Failed to unload visual pipeline in finally block: {e}")

        is_canceled = _gen_state.get('cancel', False)
        _gen_state['active'] = False
        _gen_state['cancel'] = False

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


