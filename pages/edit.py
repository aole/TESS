import os
import datetime
from PIL import Image
from fastapi import UploadFile, File, Form
from nicegui import ui, app, run

# Register the upload API route at import time
@app.post('/upload-edited-image')
async def upload_edited_image(file: UploadFile = File(...), original_path: str = Form("")):
    contents = await file.read()
    
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
        
    # Generate thumbnail
    try:
        with Image.open(output_path) as img:
            thumb = img.copy()
            thumb.thumbnail((256, 256))
            thumb_name = os.path.splitext(fname)[0] + ".webp"
            thumb_path = f"data/visual/thumbs/{thumb_name}"
            thumb.save(thumb_path, format="WEBP")
    except Exception as e:
        print(f"Failed to generate thumbnail for edited image: {e}")
        
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
                        
                    try:
                        with Image.open(output_path) as img:
                            thumb = img.copy()
                            thumb.thumbnail((256, 256))
                            thumb_name = os.path.splitext(fname)[0] + ".webp"
                            thumb_path = f"data/visual/thumbs/{thumb_name}"
                            thumb.save(thumb_path, format="WEBP")
                    except Exception as err:
                        print(f"Failed to generate thumbnail: {err}")
                        
                    app.storage.user['visual_last_image'] = output_path
                    web_path = f"/{output_path}"
                    ui.notify(f"Uploaded: {filename}", type='info')
                    ui.run_javascript(f"""
                        const iframe = document.getElementById('photopea');
                        iframe.dataset.currentPath = '{output_path}';
                        window.loadPhotopeaImage('{web_path}');
                    """)

                # Save / Export button
                ui.button('Save to Tess', icon='save', on_click=lambda: ui.run_javascript('window.exportPhotopeaImage();')).classes('save-btn').props('dense no-caps')

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

      window.exportPhotopeaImage = function() {
        const iframe = getIframe();
        if (iframe && iframe.contentWindow) {
          console.log("Requesting PNG export from Photopea...");
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

          try {
            const response = await fetch("/upload-edited-image", {
              method: "POST",
              body: formData,
            });
            if (response.ok) {
              const result = await response.json();
              console.log("Upload success:", result);
              emitEvent('photopea-saved', { path: result.path, filename: result.filename });
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
