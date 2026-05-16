import os
import torch
import gc
from diffsynth.pipelines.anima_image import AnimaImagePipeline, ModelConfig

# 1. ENVIRONMENT SETUP
os.environ["DIFFSYNTH_DOWNLOAD_SOURCE"] = "huggingface"
os.environ["DIFFSYNTH_MODEL_BASE_PATH"] = os.path.abspath("./models")

def flush():
    """Nuclear cleanup for 8GB VRAM."""
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    gc.collect()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

_cached_pipe = None


def get_pipeline(vram_limit):
    global _cached_pipe
    if _cached_pipe is None:
        print(f"--- Initializing Anima Base v1.0 on {vram_limit:.2f}GB VRAM ---")
        _cached_pipe = AnimaImagePipeline.from_pretrained(
            torch_dtype=torch.bfloat16,
            device="cuda",
            model_configs=[
                ModelConfig(
                    model_id="circlestone-labs/Anima", 
                    origin_file_pattern="split_files/diffusion_models/anima-base-v1.0.safetensors", 
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
    return _cached_pipe


def unload_pipeline():
    global _cached_pipe
    if _cached_pipe is not None:
        print("Unloading pipeline and clearing VRAM...")
        del _cached_pipe
        _cached_pipe = None
    flush()


def generate_image_task(prompt: str, negative_prompt: str, steps: int = 30, width: int = 1024, height: int = 1024, progress_callback=None, unload_after=True) -> str:
    # Calculate VRAM limit for an 8GB card (leaving a small buffer)
    vram_info = torch.cuda.mem_get_info("cuda")
    vram_limit = vram_info[1] / (1024 ** 3) - 0.5
    
    # 2. PIPELINE INITIALIZATION (or retrieval)
    pipe = get_pipeline(vram_limit)

    # 3. INFERENCE
    print(f"Generating image: {prompt[:50]}...")
    def _progress_bar_cmd(iterable, **kwargs):
        """tqdm-compatible wrapper that drives the progress_callback."""
        items = list(iterable)
        total = len(items)
        for i, item in enumerate(items):
            if progress_callback:
                try:
                    progress_callback(i, total)
                except Exception:
                    pass
            yield item
        if progress_callback:
            try:
                progress_callback(total, total)
            except Exception:
                pass

    with torch.no_grad():
        image = pipe(
            prompt, 
            negative_prompt=negative_prompt,
            num_inference_steps=steps,
            width=width,
            height=height,
            progress_bar_cmd=_progress_bar_cmd,
        )
    
    import datetime
    import json
    from PIL.PngImagePlugin import PngInfo
    
    os.makedirs("data/visual/thumbs", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"tess_{timestamp}.png"
    output_path = f"data/visual/{fname}"
    
    metadata = PngInfo()
    params = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "width": width,
        "height": height,
        "model": "Anima Base v1.0"
    }
    # Many tools like Automatic1111 use the 'parameters' text chunk.
    # We can store a JSON representation or a formatted string. JSON is robust.
    metadata.add_text("parameters", json.dumps(params, indent=2))
    
    image.save(output_path, pnginfo=metadata)
    
    # Generate and save thumbnail
    thumb = image.copy()
    thumb.thumbnail((256, 256))
    thumb_path = os.path.join("data/visual/thumbs", fname)
    thumb.save(thumb_path)
    
    print(f"Success: saved as {output_path}")
    
    # Cleanup memory if requested
    if unload_after:
        unload_pipeline()
    
    return output_path
