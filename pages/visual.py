import os
import torch
import gc
import asyncio
from nicegui import ui, run
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

def generate_image_task(prompt: str, negative_prompt: str) -> str:
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
            num_inference_steps=30,
            width=1024,
            height=1024
        )
    
    output_path = "anima_preview3_final.png"
    image.save(output_path)
    print(f"Success: saved as {output_path}")
    
    # Cleanup memory
    del pipe
    flush()
    
    return output_path

def create_page():
    ui.label('Visual Generation').classes('text-2xl font-bold mb-4')
    
    with ui.column().classes('w-full max-w-4xl mx-auto gap-4 p-4'):
        # Large textbox for positive prompt
        prompt = ui.textarea('Positive Prompt', placeholder='masterpiece, best quality, ...').classes('w-full text-lg').props('outlined rows="4"')
        prompt.value = "masterpiece, best quality, score_7, safe, 1boy, wizard robes, holding a staff, swirling nebula energy, constellations in hair, dark forest, mystical lighting, cinematic rim light"
        
        # Negative prompt and generate button
        with ui.row().classes('w-full items-start gap-4'):
            negative_prompt = ui.textarea('Negative Prompt', placeholder='worst quality, low quality, ...').classes('flex-grow').props('outlined rows="2"')
            negative_prompt.value = "worst quality, low quality, score_1, score_2, score_3, artist name, nsfw"
            
            generate_btn = ui.button('Generate', icon='brush').classes('h-[72px] px-8 py-4 text-lg bg-gradient-to-r from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600 shadow-lg')
        
        # Image container
        image_container = ui.column().classes('w-full items-center justify-center mt-8 min-h-[512px] bg-black/20 rounded-lg border border-white/10 overflow-hidden')
        
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
                output_path = await run.io_bound(generate_image_task, prompt.value, negative_prompt.value)
                
                # Update UI
                image_container.clear()
                with image_container:
                    # Append a timestamp to prevent caching issues
                    import time
                    ui.image(f"/output/{output_path}?t={time.time()}").classes('max-w-full rounded-lg shadow-xl')
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
        
        generate_btn.on('click', on_generate)
