import os
import datetime
import json
import asyncio
import re
import struct
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from fastapi import UploadFile, File, Form
from nicegui import ui, app, run
from core.session_state import SERVER_SESSION_ID
from services.visual_service import create_thumbnail
from core.generate_image import generate_anima_image, unload_pipeline as unload_image_pipeline
from core.generate_inpaint import generate_anima_inpaint_image, unload_pipeline as unload_inpaint_pipeline


_EDIT_MARKER_RE = re.compile(r'_(?:edited|edit)_\d{8}_\d{6}(?:_\d+)?')
_TRAILING_EDIT_RE = re.compile(r'_(?:edited|edit)$')
_TRAILING_TIMESTAMP_RE = re.compile(r'(?:_\d{8}_\d{6})+$')
_TIMESTAMP_STEM_RE = re.compile(r'\d{8}_\d{6}(?:_\d+)?')
_EDIT_SESSION_PSD_PATH = "data/visual/temp/edit_session.psd"
_EDIT_SESSION_KEY = "edit_server_session_id"
_VISUAL_PROMPT_SESSION_KEY = "visual_prompt_server_session_id"


def _safe_filename_stem(value: str, fallback: str = "image", max_length: int = 80) -> str:
    stem = "".join(c if c.isalnum() or c in "._-" else "_" for c in value)
    stem = re.sub(r'_+', '_', stem).strip("._-")
    if not stem:
        stem = fallback
    return stem[:max_length].rstrip("._-") or fallback


def _edited_image_filename(original_path: str, timestamp: str) -> str:
    if original_path:
        stem = os.path.splitext(os.path.basename(original_path))[0]
        if stem.startswith("tess_"):
            stem = stem[5:]
        had_edit_marker = bool(_EDIT_MARKER_RE.search(stem) or _TRAILING_EDIT_RE.search(stem))
        stem = _EDIT_MARKER_RE.sub("", stem)
        stem = _TRAILING_EDIT_RE.sub("", stem)
        if had_edit_marker and not _TIMESTAMP_STEM_RE.fullmatch(stem):
            stem = _TRAILING_TIMESTAMP_RE.sub("", stem)
        stem = _safe_filename_stem(stem)
    else:
        stem = "image"
    return f"tess_{stem}_edit_{timestamp}.png"


def _create_flat_psd_from_image(source_path: str, output_path: str = _EDIT_SESSION_PSD_PATH) -> bool:
    if not source_path or not os.path.exists(source_path):
        return False
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with Image.open(source_path) as img:
            has_alpha = img.mode in ("RGBA", "LA") or ("transparency" in img.info)
            image = img.convert("RGBA" if has_alpha else "RGB")
            width, height = image.size
            channels = image.split()
            with open(output_path, "wb") as f:
                f.write(struct.pack(">4sH6sHIIHH", b"8BPS", 1, b"\0" * 6, len(channels), height, width, 8, 3))
                f.write(struct.pack(">I", 0))  # color mode data
                f.write(struct.pack(">I", 0))  # image resources
                f.write(struct.pack(">I", 0))  # layer and mask info
                f.write(struct.pack(">H", 0))  # raw image data
                for channel in channels:
                    f.write(channel.tobytes())
        return True
    except Exception as ex:
        print(f"Failed to create temp PSD from {source_path}: {ex}")
        return False


def _create_blank_psd(width: int, height: int, output_path: str = _EDIT_SESSION_PSD_PATH) -> bool:
    # First-time edit sessions start as a real PSD sized from the visual controls.
    try:
        width = max(1, int(width))
        height = max(1, int(height))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image = Image.new("RGB", (width, height), "white")
        channels = image.split()
        with open(output_path, "wb") as f:
            f.write(struct.pack(">4sH6sHIIHH", b"8BPS", 1, b"\0" * 6, len(channels), height, width, 8, 3))
            f.write(struct.pack(">I", 0))  # color mode data
            f.write(struct.pack(">I", 0))  # image resources
            f.write(struct.pack(">I", 0))  # layer and mask info
            f.write(struct.pack(">H", 0))  # raw image data
            for channel in channels:
                f.write(channel.tobytes())
        return True
    except Exception as ex:
        print(f"Failed to create blank edit PSD: {ex}")
        return False


def _web_url(path: str) -> str:
    if not path:
        return ""
    url = f"/{path}"
    try:
        version = int(os.path.getmtime(path) * 1000)
        return f"{url}?v={version}"
    except OSError:
        return url


def _current_edit_parameters(original_path: str, image_path: str) -> dict:
    user_storage = app.storage.user

    def _as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    turbo_enabled = user_storage.get('edit_i2i_turbo_enabled', False)
    turbo_lora = _as_float(user_storage.get('edit_i2i_turbo_strength', 1.0), 1.0) if turbo_enabled else 0.0

    try:
        with Image.open(image_path) as img:
            width, height = img.size
    except Exception:
        width = user_storage.get('visual_image_width', 1024)
        height = user_storage.get('visual_image_height', 1024)

    params = {
        "prompt": user_storage.get('edit_i2i_prompt', ''),
        "negative_prompt": user_storage.get('edit_i2i_neg_prompt', ''),
        "steps": _as_int(user_storage.get('edit_i2i_steps', 30), 30),
        "width": _as_int(width, 1024),
        "height": _as_int(height, 1024),
        "seed": None,
        "cfg_scale": _as_float(user_storage.get('edit_i2i_cfg', 4.0), 4.0),
        "model": "Anima Base v1.0",
        "mode": user_storage.get('edit_last_generation_mode', 'photopea_edit'),
        "denoising_strength": _as_float(user_storage.get('edit_i2i_denoising', 0.6), 0.6),
        "turbo_lora": turbo_lora,
    }
    if original_path:
        params["input_image_path"] = original_path
    return params


def _embed_current_edit_metadata(image_path: str, original_path: str):
    try:
        metadata = PngInfo()
        metadata.add_text("parameters", json.dumps(_current_edit_parameters(original_path, image_path), indent=2))
        with Image.open(image_path) as img:
            img.save(image_path, pnginfo=metadata)
    except Exception as ex:
        print(f"Failed to embed edit metadata in {image_path}: {ex}")


# Register the upload API route at import time
@app.post('/upload-edited-image')
async def upload_edited_image(
    file: UploadFile = File(...),
    original_path: str = Form(""),
    action: str = Form("save"),
    psd_path: str = Form(""),
):
    contents = await file.read()
    
    if action == "psd":
        safe_psd_path = psd_path.replace('\\', '/')
        if safe_psd_path != _EDIT_SESSION_PSD_PATH:
            safe_psd_path = _EDIT_SESSION_PSD_PATH
        os.makedirs(os.path.dirname(safe_psd_path), exist_ok=True)
        output_path = safe_psd_path
        fname = os.path.basename(output_path)
    elif action in ("i2i", "mask"):
        os.makedirs("data/visual/temp", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "selection_mask" if action == "mask" else "i2i_input"
        fname = f"{prefix}_{timestamp}.png"
        output_path = f"data/visual/temp/{fname}"
    else:
        os.makedirs("data/visual/images", exist_ok=True)
        os.makedirs("data/visual/thumbs", exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = _edited_image_filename(original_path, timestamp)
            
        output_path = f"data/visual/images/{fname}"
        
    with open(output_path, "wb") as f:
        f.write(contents)
        
    if action not in ("i2i", "mask", "psd"):
        _embed_current_edit_metadata(output_path, original_path)
        # Generate thumbnail
        create_thumbnail(output_path)
        app.storage.user['visual_last_image'] = output_path
    elif action == "psd":
        app.storage.user['edit_session_psd_path'] = output_path
    
    return {"status": "success", "path": output_path, "filename": fname}


def get_image_files():
    visual_dir = 'data/visual/images'
    if not os.path.isdir(visual_dir):
        return []
    exts = {'.png', '.jpg', '.jpeg', '.webp'}
    try:
        files = sorted(
            [f for f in os.listdir(visual_dir)
             if os.path.isfile(os.path.join(visual_dir, f)) and os.path.splitext(f)[1].lower() in exts],
            reverse=True,
        )
        return [os.path.join(visual_dir, f).replace('\\', '/') for f in files]
    except Exception:
        return []


def extract_metadata(fpath: str):
    if not fpath or not os.path.exists(fpath):
        return None
    try:
        with Image.open(fpath) as img:
            metadata = img.text if hasattr(img, 'text') else img.info
            if metadata:
                params_str = metadata.get('parameters')
                if params_str:
                    return json.loads(params_str)
    except Exception as e:
        print(f"Error extracting metadata: {e}")
    return None


def create_page(initial_img: str = None, initial_imgs: str = None):
    user_storage = app.storage.user

    # Edit prompt text and the working PSD are server-session state.
    if user_storage.get(_EDIT_SESSION_KEY) != SERVER_SESSION_ID:
        for key in (
            'edit_i2i_prompt',
            'edit_i2i_neg_prompt',
            'edit_last_initialized_img',
            'edit_session_psd_path',
            'edit_session_source_path',
        ):
            user_storage.pop(key, None)
        try:
            os.remove(_EDIT_SESSION_PSD_PATH)
        except FileNotFoundError:
            pass
        except OSError as ex:
            print(f"Failed to remove stale edit session PSD: {ex}")
        user_storage[_EDIT_SESSION_KEY] = SERVER_SESSION_ID

    # Avoid using stale visual prompt fallbacks when edit is opened first after restart.
    if user_storage.get(_VISUAL_PROMPT_SESSION_KEY) != SERVER_SESSION_ID:
        user_storage.pop('visual_positive_prompt', None)
        user_storage.pop('visual_negative_prompt', None)

    # Resolve initial image:
    remaining_web_urls = ""
    explicit_edit_source = bool(initial_img or initial_imgs)
    session_psd_path = _EDIT_SESSION_PSD_PATH
    requested_source_path = None
    if initial_imgs:
        imgs_list = [img.strip().replace('\\', '/') for img in initial_imgs.split(',') if img.strip()]
        if imgs_list:
            initial_img = imgs_list[0]
            requested_source_path = initial_img
            remaining_imgs = imgs_list[1:]
            remaining_web_urls = ",".join([f"/{path}" for path in remaining_imgs])
    elif initial_img:
        requested_source_path = initial_img
    elif not initial_img:
        if os.path.exists(session_psd_path):
            initial_img = session_psd_path
        
    if initial_img:
        initial_img = initial_img.replace('\\', '/')
        if not os.path.exists(initial_img):
            files = get_image_files()
            initial_img = files[0] if files else None

    if explicit_edit_source and requested_source_path:
        edit_psd_path = _EDIT_SESSION_PSD_PATH
        if _create_flat_psd_from_image(requested_source_path, edit_psd_path):
            initial_img = edit_psd_path
        app.storage.user['edit_session_psd_path'] = edit_psd_path
        app.storage.user['edit_session_source_path'] = requested_source_path
    elif initial_img and initial_img.lower().endswith(".psd"):
        edit_psd_path = initial_img
    elif os.path.exists(session_psd_path):
        edit_psd_path = session_psd_path
    else:
        edit_psd_path = _EDIT_SESSION_PSD_PATH
        width = user_storage.get('visual_image_width', 1024)
        height = user_storage.get('visual_image_height', 1024)
        if _create_blank_psd(width, height, edit_psd_path):
            initial_img = edit_psd_path
        app.storage.user['edit_session_psd_path'] = edit_psd_path

    if edit_psd_path and not os.path.exists(edit_psd_path):
        app.storage.user['edit_session_psd_path'] = edit_psd_path

    # Load initial image web-accessible path
    web_url = _web_url(initial_img) if initial_img else ""
    initial_is_psd = bool(initial_img and initial_img.lower().endswith(".psd"))
    current_doc_source_path = app.storage.user.get('edit_session_source_path') if initial_is_psd else initial_img
    current_doc_source_path = current_doc_source_path or initial_img or ""

    metadata_source_path = current_doc_source_path or initial_img
    params = extract_metadata(metadata_source_path) if metadata_source_path else None
    
    # Initialize edit page i2i options.
    def init_storage_val(key, default_val):
        if key not in user_storage:
            user_storage[key] = default_val

    # Only initialize/overwrite if the image has changed
    init_key = metadata_source_path or initial_img
    last_init_img = user_storage.get('edit_last_initialized_img')
    if init_key and init_key != last_init_img:
        user_storage['edit_last_initialized_img'] = init_key
        if params:
            user_storage['edit_i2i_prompt'] = params.get('prompt', '')
            user_storage['edit_i2i_neg_prompt'] = params.get('negative_prompt', '')
            user_storage['edit_i2i_steps'] = params.get('steps', 30)
            user_storage['edit_i2i_cfg'] = params.get('cfg_scale', 4.0)
            user_storage['edit_i2i_denoising'] = params.get('denoising_strength', 0.6)
            turbo_val = params.get('turbo_lora', 0.0)
            user_storage['edit_i2i_turbo_enabled'] = turbo_val > 0.0
            user_storage['edit_i2i_turbo_strength'] = turbo_val if turbo_val > 0.0 else 1.0
        else:
            user_storage['edit_i2i_prompt'] = user_storage.get('visual_positive_prompt', '')
            user_storage['edit_i2i_neg_prompt'] = user_storage.get('visual_negative_prompt', '')
            user_storage['edit_i2i_steps'] = user_storage.get('visual_inference_steps', 30)
            user_storage['edit_i2i_cfg'] = user_storage.get('visual_cfg_scale', 4.0)
            user_storage['edit_i2i_denoising'] = user_storage.get('visual_denoising_strength', 0.6)
            user_storage['edit_i2i_turbo_enabled'] = user_storage.get('visual_turbo_lora_enabled', False)
            user_storage['edit_i2i_turbo_strength'] = user_storage.get('visual_turbo_lora_strength', 1.0)
    else:
        init_storage_val('edit_i2i_prompt', user_storage.get('visual_positive_prompt', ''))
        init_storage_val('edit_i2i_neg_prompt', user_storage.get('visual_negative_prompt', ''))
        init_storage_val('edit_i2i_steps', user_storage.get('visual_inference_steps', 30))
        init_storage_val('edit_i2i_cfg', user_storage.get('visual_cfg_scale', 4.0))
        init_storage_val('edit_i2i_denoising', user_storage.get('visual_denoising_strength', 0.6))
        init_storage_val('edit_i2i_turbo_enabled', user_storage.get('visual_turbo_lora_enabled', False))
        init_storage_val('edit_i2i_turbo_strength', user_storage.get('visual_turbo_lora_strength', 1.0))
    init_storage_val('edit_i2i_count', 1)

    generating = {'active': False, 'pending': False, 'cancel': False}



    # Custom UI Header Styling
    ui.add_head_html("""
        <style>
            .edit-container {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: calc(100vh - 60px);
                overflow: hidden;
            }
            .edit-toolbar {
                display: flex;
                align-items: center;
                gap: 16px;
                padding: 8px 16px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                background: rgba(30, 41, 59, 0.7);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
            }
            .photopea-wrapper {
                flex-grow: 1;
                width: 100%;
                padding: 12px;
                background-color: #121214;
            }
            .glass-btn {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #e2e8f0;
                transition: all 0.3s ease;
            }
            .glass-btn:hover {
                background: rgba(255, 255, 255, 0.15);
                border-color: rgba(255, 255, 255, 0.25);
            }
            .save-btn {
                background: linear-gradient(135deg, #a78bfa 0%, #db2777 100%);
                color: white;
                font-weight: 600;
                border: none;
                transition: transform 0.2s ease, filter 0.2s ease;
            }
            .save-btn:hover {
                filter: brightness(1.1);
                transform: translateY(-1px);
            }
            .stop-btn {
                background: rgba(239, 68, 68, 0.9);
                border: 1px solid rgba(248, 113, 113, 0.95);
                color: white;
            }
            .stop-btn:hover {
                background: rgba(220, 38, 38, 0.95);
                border-color: rgba(252, 165, 165, 1);
            }
        </style>
    """)

    # i2i Options Dialog
    with ui.dialog().props('position=right') as i2i_options_dialog, ui.card().classes('w-[550px] max-w-full h-screen max-h-screen p-6 gap-4 bg-[#1e1f20] border-l border-white/10 text-white rounded-none shadow-2xl'):
        with ui.row().classes('w-full items-center justify-between border-b border-white/10 pb-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('tune', size='24px').classes('text-indigo-400')
                ui.label('Image-to-Image Settings').classes('text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-indigo-400')
            ui.button(icon='close', on_click=i2i_options_dialog.close).props('flat dense round').classes('text-gray-400 hover:text-white')

        with ui.column().classes('w-full flex-grow gap-3 overflow-y-auto pr-1'):
            ui.label('Positive Prompt').classes('text-xs font-semibold text-gray-400 uppercase tracking-wider')
            pos_prompt_textarea = ui.textarea(placeholder='Positive prompt...').classes('w-full text-sm bg-black/20 border border-white/10 rounded p-2 text-white').props('outlined rows="5"').bind_value(app.storage.user, 'edit_i2i_prompt')

            ui.label('Negative Prompt').classes('text-xs font-semibold text-gray-400 uppercase tracking-wider')
            neg_prompt_textarea = ui.textarea(placeholder='Negative prompt...').classes('w-full text-sm bg-black/20 border border-white/10 rounded p-2 text-white').props('outlined rows="2"').bind_value(app.storage.user, 'edit_i2i_neg_prompt')

            # Steps and Count
            with ui.row().classes('w-full items-center gap-4 no-wrap'):
                with ui.column().classes('flex-grow gap-1'):
                    with ui.row().classes('w-full justify-between items-center'):
                        ui.label('Steps').classes('text-xs text-gray-400')
                        steps_label = ui.label(str(int(user_storage.get('edit_i2i_steps', 30)))).classes('text-xs text-indigo-400 font-mono')
                    steps_slider = ui.slider(
                        min=1, max=50, step=1,
                        on_change=lambda e: steps_label.set_text(str(int(e.value)))
                    ).classes('w-full').bind_value(app.storage.user, 'edit_i2i_steps')
                
                count_input = ui.number(
                    label='Count', value=int(user_storage.get('edit_i2i_count', 1)), min=1, max=10, format='%d'
                ).classes('w-20 text-sm').props('dense outlined dark color=indigo-400').bind_value(app.storage.user, 'edit_i2i_count')

            # Denoising Strength
            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('Denoising Strength').classes('text-xs text-gray-400')
                    denoising_label = ui.label(f"{user_storage.get('edit_i2i_denoising', 0.6):.2f}").classes('text-xs text-indigo-400 font-mono')
                denoising_slider = ui.slider(
                    min=0.01, max=1.0, step=0.01,
                    on_change=lambda e: denoising_label.set_text(f"{e.value:.2f}")
                ).classes('w-full').bind_value(app.storage.user, 'edit_i2i_denoising')

            # CFG Scale
            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('CFG Scale').classes('text-xs text-gray-400')
                    cfg_label = ui.label(f"{user_storage.get('edit_i2i_cfg', 4.0):.1f}").classes('text-xs text-indigo-400 font-mono')
                cfg_slider = ui.slider(
                    min=1.0, max=20.0, step=0.1,
                    on_change=lambda e: cfg_label.set_text(f"{e.value:.1f}")
                ).classes('w-full').bind_value(app.storage.user, 'edit_i2i_cfg')

            # Turbo LoRA
            with ui.row().classes('w-full items-center gap-2 flex-nowrap border-t border-white/5 pt-2'):
                turbo_check = ui.checkbox('Enable Turbo').classes('text-xs text-gray-400').bind_value(app.storage.user, 'edit_i2i_turbo_enabled')
                turbo_strength_slider = ui.slider(
                    min=0.1, max=2.0, step=0.05
                ).classes('flex-grow').bind_value(
                    app.storage.user, 'edit_i2i_turbo_strength'
                ).bind_enabled_from(turbo_check, 'value')
                turbo_strength_label = ui.label().classes('text-xs text-indigo-400 font-mono w-10 text-right')
                turbo_strength_label.bind_text_from(
                    turbo_strength_slider, 'value', backward=lambda v: f"{v:.2f}"
                )

        with ui.row().classes('w-full justify-end border-t border-white/10 pt-4'):
            generate_i2i_btn = ui.button(
                'Generate',
                icon='brush',
                on_click=lambda: start_i2i_generation_export()
            ).classes('save-btn px-4').props('dense')

    def handle_dialog_close(e):
        if not e.value:
            pos_prompt_textarea.update()
            neg_prompt_textarea.update()
            denoising_slider.update()
            steps_slider.update()
            cfg_slider.update()
            turbo_check.update()
            turbo_strength_slider.update()
            turbo_strength_label.update()
            count_input.update()

    i2i_options_dialog.on_value_change(handle_dialog_close)

    def set_i2i_button_generating(active: bool):
        if active:
            i2i_btn.props('icon=stop color=red')
            i2i_btn.classes(remove='glass-btn', add='stop-btn')
        else:
            i2i_btn.props('icon=brush', remove='color')
            i2i_btn.classes(remove='stop-btn', add='glass-btn')

    def reset_i2i_generation_state():
        generating['active'] = False
        generating['pending'] = False
        generating['cancel'] = False
        set_i2i_button_generating(False)

    def start_i2i_generation_export():
        if generating['active']:
            ui.notify("Generation already in progress", type='warning')
            return
        i2i_options_dialog.close()
        generating['active'] = True
        generating['pending'] = True
        generating['cancel'] = False
        set_i2i_button_generating(True)
        ui.run_javascript("window.runPhotopeaI2I();")

    def handle_i2i_toolbar_click():
        if generating['active']:
            generating['cancel'] = True
            ui.notify("Stopping generation...", type='warning', pos='bottom-right')
            return
        i2i_options_dialog.open()

    def navigate_after_psd_save(target: str):
        ui.run_javascript(f"""
            if (window.savePhotopeaPsdThenNavigate) {{
                window.savePhotopeaPsdThenNavigate('{target}');
            }} else {{
                window.location.href = '{target}';
            }}
        """)

    # Main layout container
    with ui.column().classes('edit-container'):
        # Toolbar
        with ui.row().classes('edit-toolbar w-full justify-between flex-nowrap'):
            with ui.row().classes('items-center gap-3'):
                ui.button(icon='arrow_back', on_click=lambda: navigate_after_psd_save('/visual')).props('flat dense round').classes('text-gray-300 hover:text-white').tooltip('Back to Visual')
                ui.label('Photopea Image Editor').classes('text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-pink-400')
                
            with ui.row().classes('items-center gap-3'):
                # File uploader
                async def handle_local_upload(e):
                    contents = e.content.read()
                    filename = e.name
                    
                    os.makedirs("data/visual/images", exist_ok=True)
                    os.makedirs("data/visual/thumbs", exist_ok=True)
                    
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    name, ext = os.path.splitext(filename)
                    fname = f"tess_upload_{name}_{timestamp}{ext}"
                    output_path = f"data/visual/images/{fname}"
                    
                    with open(output_path, "wb") as f:
                        f.write(contents)
                        
                    # Generate thumbnail
                    create_thumbnail(output_path)
                        
                    app.storage.user['visual_last_image'] = output_path
                    web_path = f"/{output_path}"
                    ui.notify(f"Uploaded: {filename}", type='info')
                    new_psd_path = _EDIT_SESSION_PSD_PATH
                    _create_flat_psd_from_image(output_path, new_psd_path)
                    app.storage.user['edit_session_psd_path'] = new_psd_path
                    app.storage.user['edit_session_source_path'] = output_path
                    psd_web_path = _web_url(new_psd_path)
                    ui.run_javascript(f"""
                        const iframe = document.getElementById('photopea');
                        iframe.dataset.currentPath = '{output_path}';
                        iframe.dataset.sessionPsdPath = '{new_psd_path}';
                        iframe.dataset.initialIsPsd = '1';
                        window.loadPhotopeaImage('{psd_web_path}', false);
                    """)

                # Image-to-image options and generation
                i2i_btn = ui.button(icon='brush', on_click=handle_i2i_toolbar_click).classes('glass-btn').props('dense round').tooltip('Image-to-Image')

                # Vertical Separator
                ui.element('div').classes('h-6 w-px bg-white/20 mx-1')

                # Save / Export button
                ui.button(icon='save', on_click=lambda: ui.run_javascript("window.exportPhotopeaImage('save');")).classes('save-btn').props('dense round').tooltip('Save to Tess')

        # Iframe Wrapper
        with ui.element('div').classes('photopea-wrapper'):
            iframe_html = f"""
            <iframe
              id="photopea"
              src="https://www.photopea.com"
              sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-popups allow-pointer-lock"
              style="width: 100%; height: 100%; border: 0; border-radius: 8px; box-shadow: inset 0 0 10px rgba(0,0,0,0.5);"
              {"data-pending-img=" + web_url if web_url else ""}
              {"data-pending-layers=" + remaining_web_urls if remaining_web_urls else ""}
              {"data-current-path=" + current_doc_source_path if current_doc_source_path else ""}
              data-session-psd-path="{edit_psd_path}"
              data-initial-is-psd="{"1" if initial_is_psd else "0"}"
            ></iframe>
            """
            ui.html(iframe_html, sanitize=False).classes('w-full h-full')

    # JavaScript receiver code
    ui.add_body_html("""
    <script>
    (function() {
      const iframeId = 'photopea';
      
      function getIframe() {
        return document.getElementById(iframeId);
      }

      function getSessionPsdPath() {
        const iframe = getIframe();
        return iframe ? (iframe.dataset.sessionPsdPath || 'data/visual/temp/edit_session.psd') : 'data/visual/temp/edit_session.psd';
      }

      function requestPhotopeaPsdSave() {
        if (window.photopeaPsdSaveInFlight) {
          window.photopeaPsdSaveQueued = true;
          return true;
        }

        const iframe = getIframe();
        if (!iframe || !iframe.contentWindow) {
          return false;
        }

        window.photopeaPsdSaveInFlight = true;
        window.photopeaExportPhase = 'psd';
        iframe.contentWindow.postMessage('app.activeDocument.saveToOE("psd");', "*");
        return true;
      }

      function requestPhotopeaPsdSaveAfterDone() {
        window.photopeaSavePsdAfterDone = true;
      }

      function clearPhotopeaPsdNavigationFallback() {
        if (window.photopeaPsdNavigationTimer) {
          clearTimeout(window.photopeaPsdNavigationTimer);
          window.photopeaPsdNavigationTimer = null;
        }
      }

      function finishPhotopeaPsdNavigation(targetUrl) {
        clearPhotopeaPsdNavigationFallback();
        window.photopeaNavigateAfterPsdSave = null;
        window.photopeaNavigatingAfterSavedPsd = true;
        window.location.href = targetUrl;
      }

      function schedulePhotopeaPsdNavigationFallback(targetUrl) {
        clearPhotopeaPsdNavigationFallback();
        window.photopeaPsdNavigationTimer = setTimeout(() => {
          if (window.photopeaNavigateAfterPsdSave !== targetUrl) return;
          window.photopeaPsdSaveInFlight = false;
          window.photopeaPsdSaveQueued = false;
          window.photopeaExportPhase = null;
          finishPhotopeaPsdNavigation(targetUrl);
        }, 3000);
      }

      window.savePhotopeaPsdThenNavigate = function(targetUrl) {
        window.photopeaNavigateAfterPsdSave = targetUrl;
        if (!requestPhotopeaPsdSave()) {
          window.location.href = targetUrl;
        } else {
          // Photopea can fail to answer when not ready; never trap navigation on edit.
          schedulePhotopeaPsdNavigationFallback(targetUrl);
        }
      };

      window.loadPhotopeaImage = async function(imageUrl, autosavePsd = false) {
        const iframe = getIframe();
        if (!iframe || !iframe.contentWindow) {
          return;
        }

        try {
          const response = await fetch(imageUrl);
          if (!response.ok) return;
          const buffer = await response.arrayBuffer();
          if (autosavePsd) {
            requestPhotopeaPsdSaveAfterDone();
          }
          iframe.contentWindow.postMessage(buffer, "*");
        } catch (_err) {
          return;
        }
      };

      window.loadPhotopeaLayer = async function(imageUrl) {
        const iframe = getIframe();
        if (!iframe || !iframe.contentWindow) {
          return;
        }

        try {
          const response = await fetch(imageUrl);
          if (!response.ok) return;
          const blob = await response.blob();
          
          const reader = new FileReader();
          reader.onloadend = function() {
            const dataUrl = reader.result;
            requestPhotopeaPsdSaveAfterDone();
            iframe.contentWindow.postMessage(`app.open("${dataUrl}", null, true);`, "*");
          };
          reader.readAsDataURL(blob);
        } catch (_err) {
          return;
        }
      };

      window.exportPhotopeaImage = function(action = 'save') {
        window.photopeaAction = action;
        window.photopeaExportPhase = 'image';
        if (action !== 'i2i') {
          window.photopeaSelectionMaskPath = null;
        }
        const iframe = getIframe();
        if (iframe && iframe.contentWindow) {
          iframe.contentWindow.postMessage('app.activeDocument.saveToOE("png");', "*");
        }
      };

      window.runPhotopeaI2I = function() {
        const iframe = getIframe();
        if (!iframe || !iframe.contentWindow) return;

        window.photopeaAction = 'i2i';
        window.photopeaExportPhase = 'detect-mask';
        window.photopeaSelectionMaskPath = null;

        iframe.contentWindow.postMessage(`
          (function() {
            var doc = app.activeDocument;
            var previousLayer = doc.activeLayer;
            try {
              doc.selection.bounds;

              var maskLayer = doc.artLayers.add();
              maskLayer.name = "__tess_selection_mask__";
              doc.activeLayer = maskLayer;

              var black = new SolidColor();
              black.rgb.red = 0;
              black.rgb.green = 0;
              black.rgb.blue = 0;
              var white = new SolidColor();
              white.rgb.red = 255;
              white.rgb.green = 255;
              white.rgb.blue = 255;

              doc.selection.fill(white);
              doc.selection.invert();
              doc.selection.fill(black);
              doc.selection.invert();
              doc.activeLayer = previousLayer;
              app.activeDocument.saveToOE("png");
            } catch (err) {
              try {
                for (var i = doc.layers.length - 1; i >= 0; i--) {
                  if (doc.layers[i].name === "__tess_selection_mask__") {
                    doc.layers[i].remove();
                  }
                }
                doc.activeLayer = previousLayer;
              } catch (cleanupErr) {}
              app.echoToOE("tess:no-selection");
            }
          })();
        `, "*");
      };

      window.cleanupPhotopeaSelectionMaskAndExport = function() {
        const iframe = getIframe();
        if (!iframe || !iframe.contentWindow) return;
        window.photopeaExportPhase = 'image-after-mask';
        iframe.contentWindow.postMessage(`
          (function() {
            var doc = app.activeDocument;
            for (var i = doc.layers.length - 1; i >= 0; i--) {
              if (doc.layers[i].name === "__tess_selection_mask__") {
                doc.layers[i].remove();
              }
            }
            app.activeDocument.saveToOE("png");
          })();
        `, "*");
      };

      window.addEventListener("message", async (e) => {
        if (e.origin !== "https://www.photopea.com") return;

        if (e.data === "done") {
          const iframe = getIframe();
          if (iframe) {
            let queuedPhotopeaWork = false;
            if (iframe.dataset.pendingImg) {
              queuedPhotopeaWork = true;
              const imgUrl = iframe.dataset.pendingImg;
              iframe.removeAttribute('data-pending-img');
              const autosavePsd = iframe.dataset.initialIsPsd !== '1';
              setTimeout(() => {
                window.loadPhotopeaImage(imgUrl, autosavePsd);
              }, 200);
            } else if (iframe.dataset.pendingLayers) {
              queuedPhotopeaWork = true;
              const layers = iframe.dataset.pendingLayers.split(',');
              const nextLayer = layers.shift();
              if (layers.length > 0) {
                iframe.dataset.pendingLayers = layers.join(',');
              } else {
                iframe.removeAttribute('data-pending-layers');
              }
              if (nextLayer) {
                setTimeout(() => {
                  window.loadPhotopeaLayer(nextLayer);
                }, 200);
              }
            }

            if (!queuedPhotopeaWork && !iframe.dataset.pendingImg && !iframe.dataset.pendingLayers && window.photopeaSavePsdAfterDone) {
              window.photopeaSavePsdAfterDone = false;
              setTimeout(requestPhotopeaPsdSave, 250);
            }
          }
        }

        if (e.data === "tess:no-selection") {
          window.photopeaExportPhase = 'image';
          window.photopeaSelectionMaskPath = null;
          window.exportPhotopeaImage('i2i');
          return;
        }

        if (e.data instanceof ArrayBuffer) {
          const blob = new Blob([e.data], { type: "image/png" });
          const formData = new FormData();
          
          const iframe = getIframe();
          const originalPath = iframe ? (iframe.dataset.currentPath || "") : "";
          const phase = window.photopeaExportPhase || 'image';
          const uploadAction = phase === 'psd' ? 'psd' : (phase === 'detect-mask' ? 'mask' : (window.photopeaAction || "save"));
          const blobType = uploadAction === 'psd' ? "application/octet-stream" : "image/png";
          const uploadBlob = blob.type === blobType ? blob : new Blob([e.data], { type: blobType });
          formData.append("file", uploadBlob, uploadAction === 'psd' ? "edit_session.psd" : "edited.png");
          formData.append("original_path", originalPath);
          formData.append("action", uploadAction);
          if (uploadAction === 'psd') {
            formData.append("psd_path", getSessionPsdPath());
          }

          try {
            const response = await fetch("/upload-edited-image", {
              method: "POST",
              body: formData,
            });
            if (response.ok) {
              const result = await response.json();
              if (uploadAction === 'psd') {
                window.photopeaPsdSaveInFlight = false;
                window.photopeaExportPhase = null;
                emitEvent('photopea-psd-saved', { path: result.path, filename: result.filename });
                if (window.photopeaPsdSaveQueued) {
                  window.photopeaPsdSaveQueued = false;
                  setTimeout(requestPhotopeaPsdSave, 250);
                } else if (window.photopeaNavigateAfterPsdSave) {
                  const targetUrl = window.photopeaNavigateAfterPsdSave;
                  finishPhotopeaPsdNavigation(targetUrl);
                }
              } else if (uploadAction === 'mask') {
                window.photopeaSelectionMaskPath = result.path;
                window.cleanupPhotopeaSelectionMaskAndExport();
              } else if (window.photopeaAction === 'i2i') {
                const payload = { path: result.path, filename: result.filename };
                if (window.photopeaSelectionMaskPath) {
                  payload.mask_path = window.photopeaSelectionMaskPath;
                }
                window.photopeaExportPhase = null;
                window.photopeaSelectionMaskPath = null;
                emitEvent('photopea-i2i', payload);
              } else {
                emitEvent('photopea-saved', { path: result.path, filename: result.filename });
              }
            }
          } catch (_err) {
            if (uploadAction === 'psd') {
              window.photopeaPsdSaveInFlight = false;
              window.photopeaExportPhase = null;
              if (window.photopeaNavigateAfterPsdSave) {
                finishPhotopeaPsdNavigation(window.photopeaNavigateAfterPsdSave);
              }
            }
            return;
          }
        }
      });

      window.addEventListener('pagehide', () => {
        if (window.photopeaNavigatingAfterSavedPsd) return;
        requestPhotopeaPsdSave();
      });

      document.addEventListener('click', (event) => {
        const link = event.target.closest('a[href]');
        if (!link || link.target || link.hasAttribute('download')) return;

        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin || url.pathname === window.location.pathname) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        window.savePhotopeaPsdThenNavigate(url.pathname + url.search + url.hash);
      }, true);
    })();
    </script>
    """)

    # Python receiver lambda/function
    def handle_photopea_saved(e):
        args = e.args
        if isinstance(args, dict):
            saved_path = args.get('path')
            filename = args.get('filename')
        elif isinstance(args, list) and len(args) > 0 and isinstance(args[0], dict):
            saved_path = args[0].get('path')
            filename = args[0].get('filename')
        else:
            saved_path = None
            filename = None
            
        if saved_path:
            ui.notify(f"Image saved successfully as: {filename}", type='positive')
            app.storage.user['edit_session_source_path'] = saved_path
            ui.run_javascript(f"document.getElementById('photopea').dataset.currentPath = '{saved_path}';")

    ui.on('photopea-saved', handle_photopea_saved)

    def handle_photopea_psd_saved(e):
        args = e.args
        if isinstance(args, dict):
            psd_path = args.get('path')
        elif isinstance(args, list) and len(args) > 0 and isinstance(args[0], dict):
            psd_path = args[0].get('path')
        else:
            psd_path = None

        if psd_path:
            app.storage.user['edit_session_psd_path'] = psd_path

    ui.on('photopea-psd-saved', handle_photopea_psd_saved)

    async def handle_photopea_i2i(e):
        if generating['active'] and not generating.get('pending'):
            ui.notify("Generation already in progress", type='warning')
            return
        generating['pending'] = False
            
        args = e.args
        if isinstance(args, dict):
            input_path = args.get('path')
            mask_path = args.get('mask_path')
        elif isinstance(args, list) and len(args) > 0 and isinstance(args[0], dict):
            input_path = args[0].get('path')
            mask_path = args[0].get('mask_path')
        else:
            input_path = None
            mask_path = None
            
        if not input_path or not os.path.exists(input_path):
            ui.notify("Failed to retrieve current image from Photopea", type='negative')
            reset_i2i_generation_state()
            return
        if mask_path and not os.path.exists(mask_path):
            ui.notify("Failed to retrieve selection mask from Photopea", type='negative')
            reset_i2i_generation_state()
            return
        if generating['cancel']:
            ui.notify("Generation stopped", type='warning', pos='bottom-right')
            reset_i2i_generation_state()
            return
            
        # Retrieve options
        prompt_val = user_storage.get('edit_i2i_prompt', '')
        if not prompt_val.strip():
            ui.notify("Please enter a prompt in Image-to-Image Options", type='warning')
            reset_i2i_generation_state()
            i2i_options_dialog.open()
            return
            
        neg_prompt = user_storage.get('edit_i2i_neg_prompt', '')
        steps_val = int(user_storage.get('edit_i2i_steps', 30))
        
        # Read dimensions directly from the current document image
        try:
            with Image.open(input_path) as img:
                width_val, height_val = img.size
        except Exception as ex:
            print(f"Failed to read input image dimensions: {ex}")
            width_val = 1024
            height_val = 1024

        cfg_scale_val = float(user_storage.get('edit_i2i_cfg', 4.0))
        denoising_val = float(user_storage.get('edit_i2i_denoising', 0.6))
        turbo_enabled = user_storage.get('edit_i2i_turbo_enabled', False)
        turbo_strength = float(user_storage.get('edit_i2i_turbo_strength', 1.0)) if turbo_enabled else 0.0
        user_storage['edit_last_generation_mode'] = "photopea_inpaint" if mask_path else "photopea_i2i"

        generating['active'] = True
        generating['pending'] = False
        generate_i2i_btn.props('loading')
        generate_i2i_btn.disable()
        set_i2i_button_generating(True)
        
        # Free up VRAM by unloading LLMs
        try:
            from utils.llm_client import client as llm_client
            await llm_client.unload_all_models()
        except Exception as ex:
            print(f"Failed to unload LLMs: {ex}")
            
        count_val = int(user_storage.get('edit_i2i_count', 1))
        
        try:
            os.makedirs("data/visual/temp", exist_ok=True)
            for idx in range(count_val):
                if generating['cancel']:
                    ui.notify("Generation stopped", type='warning', pos='bottom-right')
                    break

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                mode_label = "inpaint" if mask_path else "i2i"
                temp_output_path = f"data/visual/temp/{mode_label}_output_{timestamp}_{idx}.png"

                ui.notify(f"Generating {mode_label} image {idx + 1} of {count_val}...", type='info', pos='bottom-right')

                def generation_progress_callback(_current, _total):
                    if generating['cancel']:
                        return "CANCEL"
                    return None

                # Run in a background thread to prevent UI blocking
                if mask_path:
                    output_path = await run.io_bound(
                        generate_anima_inpaint_image,
                        prompt=prompt_val,
                        output_path=temp_output_path,
                        negative_prompt=neg_prompt,
                        steps=steps_val,
                        width=width_val,
                        height=height_val,
                        cfg_scale=cfg_scale_val,
                        turbo_lora=turbo_strength,
                        input_image=input_path,
                        mask_image=mask_path,
                        denoising_strength=denoising_val,
                        progress_callback=generation_progress_callback,
                        unload_after=False
                    )
                else:
                    output_path = await run.io_bound(
                        generate_anima_image,
                        prompt=prompt_val,
                        output_path=temp_output_path,
                        negative_prompt=neg_prompt,
                        steps=steps_val,
                        width=width_val,
                        height=height_val,
                        cfg_scale=cfg_scale_val,
                        turbo_lora=turbo_strength,
                        input_image=input_path,
                        denoising_strength=denoising_val,
                        progress_callback=generation_progress_callback,
                        unload_after=False
                    )
                
                if output_path and os.path.exists(output_path):
                    ui.notify(f"{mode_label} generation {idx + 1}/{count_val} completed successfully!", type='positive')
                    web_path = f"/{output_path}"
                    # Load the generated image back as a new layer in Photopea
                    ui.run_javascript(f"window.loadPhotopeaLayer('{web_path}');")
                    # Small sleep to allow Photopea to process the layer upload sequentially
                    await asyncio.sleep(0.5)
                elif generating['cancel']:
                    ui.notify("Generation stopped", type='warning', pos='bottom-right')
                    break
                else:
                    ui.notify(f"{mode_label} generation {idx + 1} failed", type='negative')
        except Exception as ex:
            import traceback
            traceback.print_exc()
            ui.notify(f"Error during generation: {ex}", type='negative')
        finally:
            # Clean up VRAM pipeline
            try:
                await run.io_bound(unload_image_pipeline)
                await run.io_bound(unload_inpaint_pipeline)
            except Exception as ex:
                print(f"Failed to unload pipeline: {ex}")
            generate_i2i_btn.props(remove='loading')
            generate_i2i_btn.enable()
            reset_i2i_generation_state()

    ui.on('photopea-i2i', handle_photopea_i2i)

    # Clean up temp directory when user navigates away or disconnects
    def cleanup_temp_dir():
        temp_dir = "data/visual/temp"
        if not os.path.isdir(temp_dir):
            return
        for fname in os.listdir(temp_dir):
            if fname.startswith("edit_") and fname.lower().endswith(".psd"):
                continue
            if not (
                fname.startswith("selection_mask_")
                or fname.startswith("i2i_input_")
                or fname.startswith("i2i_output_")
                or fname.startswith("inpaint_output_")
            ):
                continue
            try:
                os.remove(os.path.join(temp_dir, fname))
            except OSError:
                pass
    ui.context.client.on_disconnect(cleanup_temp_dir)
