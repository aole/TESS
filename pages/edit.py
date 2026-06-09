import os
import datetime
import json
from PIL import Image, ImageOps
from fastapi import UploadFile, File, Form
from nicegui import ui, app, run
from services.visual_service import create_thumbnail
from core.generate_image import generate_anima_image, unload_pipeline

# Register the upload API route at import time
@app.post('/upload-edited-image')
async def upload_edited_image(file: UploadFile = File(...), original_path: str = Form(""), action: str = Form("save")):
    contents = await file.read()
    
    if action == "i2i":
        os.makedirs("data/visual/temp", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"i2i_input_{timestamp}.png"
        output_path = f"data/visual/temp/{fname}"
    else:
        os.makedirs("data/visual/images", exist_ok=True)
        os.makedirs("data/visual/thumbs", exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if original_path:
            base = os.path.basename(original_path)
            name, ext = os.path.splitext(base)
            name = name.replace("_edited", "")
            name = name.replace("tess_", "")
            fname = f"tess_{name}_edited_{timestamp}.png"
        else:
            fname = f"tess_edited_{timestamp}.png"
            
        output_path = f"data/visual/images/{fname}"
        
    with open(output_path, "wb") as f:
        f.write(contents)
        
    if action != "i2i":
        # Generate thumbnail
        create_thumbnail(output_path)
        app.storage.user['visual_last_image'] = output_path
    
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
    # Resolve initial image:
    remaining_web_urls = ""
    if initial_imgs:
        imgs_list = [img.strip().replace('\\', '/') for img in initial_imgs.split(',') if img.strip()]
        if imgs_list:
            initial_img = imgs_list[0]
            remaining_imgs = imgs_list[1:]
            remaining_web_urls = ",".join([f"/{path}" for path in remaining_imgs])
    elif not initial_img:
        initial_img = app.storage.user.get('visual_last_image')
        
    if initial_img:
        initial_img = initial_img.replace('\\', '/')
        if not os.path.exists(initial_img):
            files = get_image_files()
            initial_img = files[0] if files else None

    # Load initial image web-accessible path
    web_url = f"/{initial_img}" if initial_img else ""

    params = extract_metadata(initial_img) if initial_img else None
    
    # Initialize edit page i2i options
    user_storage = app.storage.user
    
    def init_storage_val(key, default_val):
        if key not in user_storage:
            user_storage[key] = default_val

    # Only initialize/overwrite if the image has changed
    last_init_img = user_storage.get('edit_last_initialized_img')
    if initial_img and initial_img != last_init_img:
        user_storage['edit_last_initialized_img'] = initial_img
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
        </style>
    """)

    # i2i Options Dialog
    with ui.dialog() as i2i_options_dialog, ui.card().classes('w-[550px] max-w-full p-6 gap-4 bg-[#1e1f20] border border-white/10 text-white rounded-xl shadow-2xl'):
        with ui.row().classes('w-full items-center justify-between border-b border-white/10 pb-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('tune', size='24px').classes('text-indigo-400')
                ui.label('Image-to-Image Settings').classes('text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-indigo-400')
            ui.button(icon='close', on_click=i2i_options_dialog.close).props('flat dense round').classes('text-gray-400 hover:text-white')

        with ui.column().classes('w-full gap-3 overflow-y-auto max-h-[70vh] pr-1'):
            ui.label('Positive Prompt').classes('text-xs font-semibold text-gray-400 uppercase tracking-wider')
            pos_prompt_textarea = ui.textarea(placeholder='Positive prompt...').classes('w-full text-sm bg-black/20 border border-white/10 rounded p-2 text-white').props('outlined rows="5"').bind_value(app.storage.user, 'edit_i2i_prompt')

            ui.label('Negative Prompt').classes('text-xs font-semibold text-gray-400 uppercase tracking-wider')
            neg_prompt_textarea = ui.textarea(placeholder='Negative prompt...').classes('w-full text-sm bg-black/20 border border-white/10 rounded p-2 text-white').props('outlined rows="2"').bind_value(app.storage.user, 'edit_i2i_neg_prompt')

            # Denoising Strength
            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('Denoising Strength').classes('text-xs text-gray-400')
                    denoising_label = ui.label(f"{user_storage.get('edit_i2i_denoising', 0.6):.2f}").classes('text-xs text-indigo-400 font-mono')
                denoising_slider = ui.slider(
                    min=0.01, max=1.0, step=0.01,
                    on_change=lambda e: denoising_label.set_text(f"{e.value:.2f}")
                ).classes('w-full').bind_value(app.storage.user, 'edit_i2i_denoising')

            # Steps
            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('Steps').classes('text-xs text-gray-400')
                    steps_label = ui.label(str(int(user_storage.get('edit_i2i_steps', 30)))).classes('text-xs text-indigo-400 font-mono')
                steps_slider = ui.slider(
                    min=1, max=50, step=1,
                    on_change=lambda e: steps_label.set_text(str(int(e.value)))
                ).classes('w-full').bind_value(app.storage.user, 'edit_i2i_steps')

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

    def handle_dialog_close(e):
        if not e.value:
            pos_prompt_textarea.update()
            neg_prompt_textarea.update()
            denoising_slider.update()
            steps_slider.update()
            cfg_slider.update()
            turbo_check.update()
            turbo_strength_slider.update()

    i2i_options_dialog.on_value_change(handle_dialog_close)

    # Main layout container
    with ui.column().classes('edit-container'):
        # Toolbar
        with ui.row().classes('edit-toolbar w-full justify-between flex-nowrap'):
            with ui.row().classes('items-center gap-3'):
                ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/visual')).props('flat dense round').classes('text-gray-300 hover:text-white').tooltip('Back to Visual')
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
                    ui.run_javascript(f"""
                        const iframe = document.getElementById('photopea');
                        iframe.dataset.currentPath = '{output_path}';
                        window.loadPhotopeaImage('{web_path}');
                    """)

                # Run i2i button
                run_i2i_btn = ui.button(icon='brush', on_click=lambda: ui.run_javascript("window.exportPhotopeaImage('i2i');")).classes('glass-btn').props('dense round').tooltip('Run Image-to-Image (i2i) on current image')

                # Edit i2i options button
                ui.button(icon='tune', on_click=i2i_options_dialog.open).classes('glass-btn').props('dense round').tooltip('Edit i2i Options')

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
              style="width: 100%; height: 100%; border: 0; border-radius: 8px; box-shadow: inset 0 0 10px rgba(0,0,0,0.5);"
              {"data-pending-img=" + web_url if web_url else ""}
              {"data-pending-layers=" + remaining_web_urls if remaining_web_urls else ""}
              {"data-current-path=" + initial_img if initial_img else ""}
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
      
      window.loadPhotopeaImage = async function(imageUrl) {
        console.log("Loading image into Photopea:", imageUrl);
        const iframe = getIframe();
        if (!iframe || !iframe.contentWindow) {
          console.error("Photopea iframe not found");
          return;
        }
        
        try {
          const response = await fetch(imageUrl);
          if (!response.ok) throw new Error("Fetch failed: " + response.statusText);
          const buffer = await response.arrayBuffer();
          iframe.contentWindow.postMessage(buffer, "*");
          console.log("Sent image buffer to Photopea");
        } catch (err) {
          console.error("Failed to load image into Photopea:", err);
        }
      };

      window.loadPhotopeaLayer = async function(imageUrl) {
        console.log("Loading layer into Photopea:", imageUrl);
        const iframe = getIframe();
        if (!iframe || !iframe.contentWindow) {
          console.error("Photopea iframe not found");
          return;
        }
        
        try {
          const response = await fetch(imageUrl);
          if (!response.ok) throw new Error("Fetch failed: " + response.statusText);
          const blob = await response.blob();
          
          const reader = new FileReader();
          reader.onloadend = function() {
            const dataUrl = reader.result;
            iframe.contentWindow.postMessage(`app.open("${dataUrl}", null, true);`, "*");
            console.log("Sent layer script to Photopea");
          };
          reader.readAsDataURL(blob);
        } catch (err) {
          console.error("Failed to load layer into Photopea:", err);
        }
      };

      window.exportPhotopeaImage = function(action = 'save') {
        window.photopeaAction = action;
        const iframe = getIframe();
        if (iframe && iframe.contentWindow) {
          console.log("Requesting PNG export from Photopea for action:", action);
          iframe.contentWindow.postMessage('app.activeDocument.saveToOE("png");', "*");
        }
      };

      window.addEventListener("message", async (e) => {
        if (e.origin !== "https://www.photopea.com") return;

        if (e.data === "done") {
          console.log("Photopea ready");
          const iframe = getIframe();
          if (iframe) {
            if (iframe.dataset.pendingImg) {
              const imgUrl = iframe.dataset.pendingImg;
              iframe.removeAttribute('data-pending-img');
              setTimeout(() => {
                window.loadPhotopeaImage(imgUrl);
              }, 200);
            } else if (iframe.dataset.pendingLayers) {
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
          }
        }

        if (e.data instanceof ArrayBuffer) {
          console.log("Received save ArrayBuffer from Photopea");
          const blob = new Blob([e.data], { type: "image/png" });
          const formData = new FormData();
          
          const iframe = getIframe();
          const originalPath = iframe ? (iframe.dataset.currentPath || "") : "";
          formData.append("file", blob, "edited.png");
          formData.append("original_path", originalPath);
          formData.append("action", window.photopeaAction || "save");

          try {
            const response = await fetch("/upload-edited-image", {
              method: "POST",
              body: formData,
            });
            if (response.ok) {
              const result = await response.json();
              console.log("Upload success:", result);
              if (window.photopeaAction === 'i2i') {
                emitEvent('photopea-i2i', { path: result.path, filename: result.filename });
              } else {
                emitEvent('photopea-saved', { path: result.path, filename: result.filename });
              }
            } else {
              console.error("Upload error:", response.statusText);
            }
          } catch (err) {
            console.error("Upload fetch error:", err);
          }
        }
      });
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
            ui.run_javascript(f"document.getElementById('photopea').dataset.currentPath = '{saved_path}';")

    ui.on('photopea-saved', handle_photopea_saved)

    generating = {'active': False}

    async def handle_photopea_i2i(e):
        if generating['active']:
            ui.notify("Generation already in progress", type='warning')
            return
            
        args = e.args
        if isinstance(args, dict):
            input_path = args.get('path')
        elif isinstance(args, list) and len(args) > 0 and isinstance(args[0], dict):
            input_path = args[0].get('path')
        else:
            input_path = None
            
        if not input_path or not os.path.exists(input_path):
            ui.notify("Failed to retrieve current image from Photopea", type='negative')
            return
            
        # Retrieve options
        prompt_val = user_storage.get('edit_i2i_prompt', '')
        if not prompt_val.strip():
            ui.notify("Please enter a prompt in Image-to-Image Options", type='warning')
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

        generating['active'] = True
        run_i2i_btn.props('loading')
        run_i2i_btn.disable()
        
        # Free up VRAM by unloading LLMs
        try:
            from utils.llm_client import client as llm_client
            await llm_client.unload_all_models()
        except Exception as ex:
            print(f"Failed to unload LLMs: {ex}")
            
        ui.notify("Generating i2i image...", type='info', pos='bottom-right')
        
        try:
            os.makedirs("data/visual/temp", exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_output_path = f"data/visual/temp/i2i_output_{timestamp}.png"

            # Run in a background thread to prevent UI blocking
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
                unload_after=False
            )
            
            if output_path and os.path.exists(output_path):
                ui.notify("i2i generation completed successfully!", type='positive')
                web_path = f"/{output_path}"
                # Load the generated image back as a new layer in Photopea
                ui.run_javascript(f"window.loadPhotopeaLayer('{web_path}');")
            else:
                ui.notify("i2i generation failed", type='negative')
        except Exception as ex:
            import traceback
            traceback.print_exc()
            ui.notify(f"Error during i2i generation: {ex}", type='negative')
        finally:
            # Clean up VRAM pipeline
            try:
                await run.io_bound(unload_pipeline)
            except Exception as ex:
                print(f"Failed to unload pipeline: {ex}")
            generating['active'] = False
            run_i2i_btn.props(remove='loading')
            run_i2i_btn.enable()

    ui.on('photopea-i2i', handle_photopea_i2i)

    # Clean up temp directory when user navigates away or disconnects
    def cleanup_temp_dir():
        import shutil
        shutil.rmtree("data/visual/temp", ignore_errors=True)
    ui.context.client.on_disconnect(cleanup_temp_dir)
