import os
import torch
import gc
import asyncio
from nicegui import ui, run, app
from diffsynth.pipelines.anima_image import AnimaImagePipeline, ModelConfig

# 1. ENVIRONMENT SETUP
os.environ["DIFFSYNTH_DOWNLOAD_SOURCE"] = "huggingface"
os.environ["DIFFSYNTH_MODEL_BASE_PATH"] = os.path.abspath("./models")

def flush():
    """Nuclear cleanup for 8GB VRAM."""
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    gc.collect()
    torch.cuda.empty_cache()

def generate_image_task(prompt: str, negative_prompt: str, steps: int = 30, width: int = 1024, height: int = 1024) -> str:
    # Calculate VRAM limit for an 8GB card (leaving a small buffer)
    vram_limit = torch.cuda.mem_get_info("cuda")[1] / (1024 ** 3) - 0.5
    print(f"--- Initializing Anima Preview 3 on {vram_limit:.2f}GB VRAM ---")

    # 2. PIPELINE INITIALIZATION
    pipe = AnimaImagePipeline.from_pretrained(
        torch_dtype=torch.bfloat16,
        device="cuda",
        model_configs=[
            ModelConfig(
                model_id="circlestone-labs/Anima", 
                origin_file_pattern="split_files/diffusion_models/anima-preview3-base.safetensors", 
            ),
            ModelConfig(
                model_id="circlestone-labs/Anima", 
                origin_file_pattern="split_files/text_encoders/qwen_3_06b_base.safetensors", 
            ),
            ModelConfig(
                model_id="circlestone-labs/Anima", 
                origin_file_pattern="split_files/vae/qwen_image_vae.safetensors", 
            ),
        ],
        tokenizer_config=ModelConfig(model_id="Qwen/Qwen3-0.6B", origin_file_pattern="./"),
        tokenizer_t5xxl_config=ModelConfig(model_id="aoleb/t5-v1_1-xxl-tokenizer", origin_file_pattern="./"),
        vram_limit=vram_limit,
    )

    # 3. INFERENCE
    print("Generating image...")
    with torch.no_grad():
        image = pipe(
            prompt, 
            negative_prompt=negative_prompt,
            num_inference_steps=steps,
            width=width,
            height=height
        )
    
    import datetime
    os.makedirs("data/visual", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"data/visual/tess_{timestamp}.png"
    image.save(output_path)
    print(f"Success: saved as {output_path}")
    
    # Cleanup memory
    del pipe
    flush()
    
    return output_path

def create_page():
    if 'visual_positive_prompt' not in app.storage.user:
        app.storage.user['visual_positive_prompt'] = "masterpiece, best quality, score_7, safe, abandoned cathedral, nature reclaiming architecture, vines and flowers, shafts of sunlight, dust particles, tranquil atmosphere, Studio Ghibli inspired"
    if 'visual_negative_prompt' not in app.storage.user:
        app.storage.user['visual_negative_prompt'] = "worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts, sepia"
    if 'visual_image_size' not in app.storage.user:
        app.storage.user['visual_image_size'] = '1024x1024'
    if 'visual_inference_steps' not in app.storage.user:
        app.storage.user['visual_inference_steps'] = 30

    with ui.row().classes('w-full max-w-screen-2xl mx-auto gap-6 p-4 flex-nowrap items-start'):
        # Left column (Image - 70%)
        with ui.column().classes('rounded-lg border border-white/10 overflow-hidden bg-black/20 items-center justify-center relative').style('flex: 7; min-height: 768px;') as image_container:
            last_image = app.storage.user.get('visual_last_image')
            if last_image and os.path.exists(last_image):
                ui.image(f"/{last_image}").classes('w-full h-full object-contain rounded-lg shadow-xl')
            else:
                ui.icon('image', size='64px').classes('text-white/10 mb-4')
                ui.label('Generated image will appear here').classes('text-white/30 text-lg')
            
        # Right column (Settings - 30%)
        with ui.column().classes('gap-6').style('flex: 3;'):
            # Large textbox for positive prompt
            prompt = ui.textarea('Positive Prompt', placeholder='masterpiece, best quality, ...').classes('w-full text-lg').props('outlined rows="10"').bind_value(app.storage.user, 'visual_positive_prompt')
            
            # Negative prompt
            negative_prompt = ui.textarea('Negative Prompt', placeholder='worst quality, low quality, ...').classes('w-full').props('outlined rows="4"').bind_value(app.storage.user, 'visual_negative_prompt')
            
            # Image Size
            with ui.column().classes('w-full gap-1'):
                ui.label('Image Size').classes('text-sm text-gray-400')
                image_size = ui.select(
                    options={'1024x1024': '1024 x 1024 (1:1)', '896x1152': '896 x 1152 (3:4)', '1152x896': '1152 x 896 (4:3)'}
                ).classes('w-full').bind_value(app.storage.user, 'visual_image_size')
                
            # Inference steps slider
            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('Inference Steps').classes('text-sm text-gray-400')
                    steps_label = ui.label(str(app.storage.user['visual_inference_steps'])).classes('text-sm text-gray-300 font-mono')
                steps = ui.slider(min=1, max=50, on_change=lambda e: steps_label.set_text(str(int(e.value)))).classes('w-full').bind_value(app.storage.user, 'visual_inference_steps')
            
            # Buttons
            with ui.row().classes('w-full gap-4 mt-2 flex-nowrap'):
                generate_btn = ui.button('Generate', icon='brush').classes('flex-grow h-16 text-xl bg-gradient-to-r from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600 shadow-lg')
                clear_btn = ui.button(icon='delete').classes('w-16 h-16 bg-red-500/20 text-red-400 hover:bg-red-500/40 shadow-lg').tooltip('Clear Image')
        
        async def on_generate():
            if not prompt.value:
                ui.notify('Please enter a positive prompt', type='warning')
                return
                
            generate_btn.disable()
            ui.notify('Generating image... This may take a minute or two.', type='info', timeout=5000)
            image_container.clear()
            
            with image_container:
                ui.spinner('dots', size='xl', color='primary')
            
            try:
                # Run the generation task in a separate thread to not block the UI
                w_str, h_str = image_size.value.split('x')
                output_path = await run.io_bound(generate_image_task, prompt.value, negative_prompt.value, int(steps.value), int(w_str), int(h_str))
                
                # Update UI
                app.storage.user['visual_last_image'] = output_path
                image_container.clear()
                with image_container:
                    ui.image(f"/{output_path}").classes('w-full h-full object-contain rounded-lg shadow-xl')
                ui.notify('Image generated successfully!', type='positive')
            except Exception as e:
                import traceback
                traceback.print_exc()
                image_container.clear()
                with image_container:
                    ui.label(f'Error: {str(e)}').classes('text-red-400')
                ui.notify(f'Failed to generate image: {str(e)}', type='negative')
            finally:
                generate_btn.enable()
        
        def on_clear():
            app.storage.user['visual_last_image'] = None
            image_container.clear()
            with image_container:
                ui.icon('image', size='64px').classes('text-white/10 mb-4')
                ui.label('Generated image will appear here').classes('text-white/30 text-lg')
                
        generate_btn.on('click', on_generate)
        clear_btn.on('click', on_clear)
