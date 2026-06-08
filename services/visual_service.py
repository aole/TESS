import os
import asyncio
import datetime
import json
import re
import gc
import itertools
import io
from PIL import Image
from pathlib import Path
from nicegui import ui, run, app
from core.generate_image import generate_anima_image, unload_pipeline
from utils.llm_client import client as llm_client
from core.modify_image import modify_image as core_modify_image, unload_session as unload_modify_image_session

def parse_resolution(res_str: str, default: tuple = (1024, 1024)) -> tuple[int, int]:
    try:
        w, h = map(int, res_str.split('x'))
        return w, h
    except (ValueError, AttributeError):
        return default

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
        ui.notify('Failed to generate thumbnail', type='error')

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

_cached_upsampler = None
_cached_upsampler_tile = None

# Retrieve or initialize the cached Real-ESRGAN upsampler instance.
def get_upsampler(tile: int):
    global _cached_upsampler, _cached_upsampler_tile
    if _cached_upsampler is None or _cached_upsampler_tile != tile:
        # Exception: Import heavy ML dependencies inline to speed up startup load times
        from core.upscale_realesrgan_anime import create_upsampler, MODEL_NAME, MODEL_URL, download_file
        weights_dir = Path("models/realesrgan")
        model_path = weights_dir / f"{MODEL_NAME}.pth"
        download_file(MODEL_URL, model_path)
        
        _cached_upsampler = create_upsampler(
            model_path=model_path,
            tile=tile,
            tile_pad=10,
            pre_pad=10,
            fp32=False,
            gpu_id=None
        )
        _cached_upsampler_tile = tile
    return _cached_upsampler

# Unload the upsampler from memory and clear PyTorch CUDA cache.
def unload_upsampler():
    global _cached_upsampler, _cached_upsampler_tile
    if _cached_upsampler is not None:
        print("Unloading upsampler...")
        _cached_upsampler = None
        _cached_upsampler_tile = None
        # Exception: Import heavy PyTorch library inline to avoid memory footprint during startup
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    gc.collect()

# Upscale a single image file using the cached upsampler and generate a thumbnail.
def upscale_image_file(fpath: str, outscale: float, tile: int) -> str:
    # Exception: Import heavy ML dependency inline to load on-demand when upscaling
    from core.upscale_realesrgan_anime import upscale_image
    output_path = new_visual_output_path()
    upsampler = get_upsampler(tile=tile)
    success = upscale_image(
        upsampler=upsampler,
        input_path=Path(fpath),
        output_path=Path(output_path),
        outscale=outscale,
        alpha_upsampler="realesrgan"
    )
    if not success:
        raise RuntimeError("Upscaling failed.")
    create_thumbnail(output_path)
    return output_path


_HIDDEN_IMAGES_FILE = 'data/visual/hidden_images.json'

def get_hidden_images() -> list:
    if not os.path.exists(_HIDDEN_IMAGES_FILE):
        return []
    try:
        with open(_HIDDEN_IMAGES_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as e:
        ui.notify(f'Failed to load hidden images: {e}', type='error')
    return []

def set_hidden_images(hidden_list: list):
    try:
        os.makedirs(os.path.dirname(_HIDDEN_IMAGES_FILE), exist_ok=True)
        with open(_HIDDEN_IMAGES_FILE, 'w') as f:
            json.dump(hidden_list, f, indent=4)
    except Exception as e:
        ui.notify(f'Failed to save hidden images: {e}', type='error')

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


# Shared state is managed dynamically per client connection/session
_initialized_users = set()

class VisualPageState:
    def __init__(self, client):
        self.client = client
        self.grid_open = True
        self.grid_element_ref = None
        
        self.current_page = 1
        self.page_size = 12

        self.selection_active = False
        self.selected_images = set()
        self.cells = {}
        
        self.toggle_btn = None
        self.delete_btn = None
        self.hide_btn = None
        self.edit_layers_btn = None
        self.count_label = None

        self.current_image = None

        self.gen_active = False
        self.gen_cancel = False
        self.gen_idx = 0
        self.gen_total = 0
        self.gen_pct = 0
        self.batch_prefix = ""
        
        self.image_container = None
        self.global_idx = 0
        self.global_total = 0
        
        self.generate_btn = None
        self.queue_btn = None
        self.itoi_btn = None
        self.remove_bg_btn = None
        self.remove_bg_status = None
        self.upscale_btn = None
        self.upscale_status = None
        
        self.progress_sidebar = None
        self.progress_sidebar_label = None
        self.progress_sidebar_bar = None
        
        self.generation_queue = []
        self.settings_ui = {}

        # Layout UI Callbacks registered from visual.py
        self.show_history = None
        self.show_image = None
        self.show_placeholder = None
        self.update_progress_labels_cb = None
        self.update_queue_ui_cb = None

    def update_queue_ui(self):
        if self.update_queue_ui_cb:
            self.update_queue_ui_cb()

    def update_progress_labels(self):
        try:
            if not self.client or self.client._deleted or not self.gen_active:
                return
                
            g_idx = self.global_idx
            g_tot = self.global_total
            
            if self.progress_sidebar_label:
                self.progress_sidebar_label.set_text(
                    f"Generating {g_idx} of {g_tot} (Preparing...)"
                )
        except Exception:
            pass

    def enqueue_job(
        self,
        raw_prompt_str: str,
        neg_prompt: str,
        steps_val: int,
        size_val: str,
        batch_count_val: int,
        cfg_scale_val=None,
        turbo_lora_val=None,
        input_image_val=None,
        denoising_strength_val: float = 1.0
    ) -> bool:
        w, h = parse_resolution(size_val, default=(0, 0))
        if w == 0 or h == 0:
            ui.notify(f"Invalid image resolution: {size_val}", type='warning')
            return False
        pixels = w * h
        if pixels < 512 * 512 or pixels > 1536 * 1536:
            ui.notify(f"Resolution {w}x{h} ({pixels} pixels) is outside the supported range of 512² to 1536² pixels.", type='warning')
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
            'upscale_auto': app.storage.user.get('visual_upscale_auto', False),
            'upscale_scale': float(app.storage.user.get('visual_upscale_scale', 2.0)),
            'upscale_tile': int(app.storage.user.get('visual_upscale_tile', 0)),
            'cfg_scale': cfg_scale_val,
            'turbo_lora': turbo_lora_val,
            'input_image': input_image_val,
            'denoising_strength': denoising_strength_val,
        }
        self.generation_queue.append(job)
        self.update_queue_ui()
        if self.gen_active:
            self.global_total += len(expanded_prompts)
            self.update_progress_labels()
        return True

    async def regenerate_image(self, fpath: str):
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
            
            success = self.enqueue_job(prompt_val, neg_prompt, steps_val, size_val, 1, cfg_scale_val=cfg_scale_val, turbo_lora_val=turbo_lora_val)
            if success:
                if self.gen_active:
                    ui.notify('Regeneration added to queue.', type='info')
                else:
                    ui.notify('Regenerating from metadata...', type='info')
                    await self.on_generate()
            
        except Exception as e:
            ui.notify(f"Could not read metadata: {e}", type='negative')

    def load_metadata(self, fpath: str):
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
                self.settings_ui['prompt'].value = params.get('prompt', '')
                self.settings_ui['negative_prompt'].value = params.get('negative_prompt', '')
                self.settings_ui['steps'].value = params.get('steps', 30)
                w = int(params.get('width', w))
                h = int(params.get('height', h))
                
                cfg_val = params.get('cfg_scale', 4.0)
                self.settings_ui['cfg_scale_slider'].value = cfg_val
                self.settings_ui['cfg_scale_label'].set_text(f"{cfg_val:.1f}")
                
                turbo_val = params.get('turbo_lora', 0.0)
                if turbo_val > 0.0:
                    self.settings_ui['turbo_checkbox'].value = True
                    self.settings_ui['turbo_strength_slider'].value = turbo_val
                    self.settings_ui['turbo_strength_label'].set_text(f"{turbo_val:.2f}")
                else:
                    self.settings_ui['turbo_checkbox'].value = False
            else:
                ui.notify('No generation metadata found, loaded image dimensions instead.', type='warning')

            if w is not None and h is not None:
                image_width = self.settings_ui['image_width']
                image_height = self.settings_ui['image_height']
                
                _update_select_options(image_width, w)
                _update_select_options(image_height, h)
                
                image_width.value = w
                image_height.value = h

            if has_params:
                ui.notify('Parameters loaded from metadata.', type='info')
            
        except Exception as e:
            ui.notify(f"Could not read metadata: {e}", type='negative')

    async def on_generate(self):
        if self.gen_active:
            return
            
        user_storage = app.storage.user
        def safe_notify(msg, **kwargs):
            try:
                active_client = self.client
                if active_client and not active_client._deleted:
                    active_client.notify(msg, **kwargs)
            except Exception:
                pass

        self.gen_active = True
        self.gen_cancel = False
        
        # Show sidebar progress UI
        if self.progress_sidebar:
            self.progress_sidebar.classes(remove='hidden')
        if self.progress_sidebar_bar:
            self.progress_sidebar_bar.set_value(0)
            
        gen_btn = self.generate_btn
        if gen_btn:
            gen_btn.props('color=red icon=stop')
            gen_btn.set_text('Stop')
            gen_btn.classes(remove='from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600', add='from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600')
        
        self.grid_element_ref = None
        
        self.global_idx = 0
        self.global_total = sum(len(job['prompts']) for job in self.generation_queue)
        
        # Free up VRAM by unloading any active LLMs
        try:
            await llm_client.unload_all_models()
        except Exception as e:
            print(f"Failed to unload LLMs before visual generation: {e}")

        loop = asyncio.get_event_loop()

        def on_progress(step: int, total: int):
            if self.gen_cancel:
                return "CANCEL"
            if total == 0:
                return
            pct = min(round(step / total * 100), 100)
            self.gen_pct = pct
            
            def _update():
                try:
                    active_client = self.client
                    if not active_client or active_client._deleted:
                        return
                    if self.progress_sidebar_bar:
                        self.progress_sidebar_bar.set_value(pct / 100)
                    if self.progress_sidebar_label:
                        g_idx = self.global_idx
                        g_tot = self.global_total
                        self.progress_sidebar_label.set_text(
                            f"Generating {g_idx} of {g_tot} (Step {step}/{total})"
                        )
                except Exception:
                    pass
            loop.call_soon_threadsafe(_update)

        try:
            while self.generation_queue and not self.gen_cancel:
                job = self.generation_queue.pop(0)
                self.update_queue_ui()
                
                raw_prompts = job['prompts']
                total_prompts = len(raw_prompts)
                
                self.grid_element_ref = None
                self.gen_total = total_prompts
                self.gen_pct = 0
                
                for idx, current_p in enumerate(raw_prompts):
                    if self.gen_cancel:
                        break
                        
                    self.global_idx += 1
                    self.gen_idx = idx
                    self.batch_prefix = f"[{self.global_idx}/{self.global_total}] "
                    self.gen_pct = 0
                    
                    if self.update_progress_labels_cb:
                        self.update_progress_labels_cb()

                    try:
                        w, h = parse_resolution(job['image_size'])
                        output_path = await run.io_bound(
                            generate_image_task,
                            current_p,
                            job['negative_prompt'],
                            job['steps'],
                            w,
                            h,
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

                        if job.get('upscale_auto'):
                            safe_notify('Upscaling image...', type='info', pos='bottom-right', timeout=1500)
                            try:
                                scale_val = job.get('upscale_scale', 2.0)
                                tile_val = job.get('upscale_tile', 0)
                                output_path = await run.io_bound(upscale_image_file, output_path, scale_val, tile_val)
                            except Exception as tool_exc:
                                safe_notify(f'Upscaling failed: {tool_exc}', type='negative')
                            finally:
                                await run.io_bound(unload_upsampler)

                        user_storage['visual_last_image'] = output_path
                        
                        active_client = self.client
                        
                        if active_client and not active_client._deleted:
                            if self.grid_open and self.show_history:
                                self.current_page = 1
                                self.grid_element_ref = None
                                self.show_history()
                            elif not self.current_image and self.show_image:
                                self.show_image(f'/{output_path}')

                        if total_prompts == 1:
                            safe_notify('Image generated successfully!', type='positive')
                        else:
                            safe_notify(f'Generated {idx+1}/{total_prompts}', type='positive', pos='bottom-right', timeout=2000)

                    except Exception as e:
                        # Exception: Import traceback inline in error handler to avoid overhead on startup
                        import traceback
                        traceback.print_exc()
                        safe_notify(f'Failed to generate image {idx+1}: {str(e)}', type='negative')
        
        finally:
            try:
                await run.io_bound(unload_pipeline)
            except Exception as e:
                print(f"Failed to unload visual pipeline in finally block: {e}")

            is_canceled = self.gen_cancel
            self.gen_active = False
            self.gen_cancel = False

            active_client = self.client
            if active_client and not active_client._deleted:
                # Hide sidebar progress UI
                if self.progress_sidebar:
                    self.progress_sidebar.classes(add='hidden')

                gen_btn = self.generate_btn
                if gen_btn:
                    gen_btn.enable()
                    gen_btn.props('color=primary icon=brush')
                    gen_btn.set_text('Generate')
                    gen_btn.classes(add='from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600', remove='from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600')
                
                self.update_queue_ui()

                if not self.grid_open and not self.current_image:
                    last = user_storage.get('visual_last_image')
                    if last and os.path.exists(last):
                        if self.show_image:
                            self.show_image(f'/{last}')
                    else:
                        if self.show_placeholder:
                            self.show_placeholder()
                
                if is_canceled:
                    safe_notify('Generation stopped.', type='warning')
                elif total_prompts > 1:
                    safe_notify(f'Batch processing of {total_prompts} prompts complete.', type='info')
