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

# Monkey patch AnimaImagePipeline.__call__ to support intermediate previews.
@torch.no_grad()
def custom_anima_call(
    self,
    prompt: str = "",
    negative_prompt: str = "",
    cfg_scale: float = 4.0,
    input_image = None,
    denoising_strength: float = 1.0,
    height: int = 1024,
    width: int = 1024,
    seed: int = None,
    rand_device: str = "cpu",
    num_inference_steps: int = 30,
    sigma_shift: float = None,
    progress_bar_cmd = None,
    preview_callback = None,
    preview_interval = 2,
):
    from tqdm import tqdm
    if progress_bar_cmd is None:
        progress_bar_cmd = tqdm

    # Scheduler
    self.scheduler.set_timesteps(num_inference_steps, denoising_strength=denoising_strength, shift=sigma_shift)
    
    # Parameters
    inputs_posi = {
        "prompt": prompt,
    }
    inputs_nega = {
        "negative_prompt": negative_prompt,
    }
    inputs_shared = {
        "cfg_scale": cfg_scale,
        "input_image": input_image, "denoising_strength": denoising_strength,
        "height": height, "width": width,
        "seed": seed, "rand_device": rand_device,
        "num_inference_steps": num_inference_steps,
    }
    for unit in self.units:
        inputs_shared, inputs_posi, inputs_nega = self.unit_runner(unit, self, inputs_shared, inputs_posi, inputs_nega)

    # Denoise
    self.load_models_to_device(self.in_iteration_models)
    models = {name: getattr(self, name) for name in self.in_iteration_models}
    for progress_id, timestep in enumerate(progress_bar_cmd(self.scheduler.timesteps)):
        timestep = timestep.unsqueeze(0).to(dtype=self.torch_dtype, device=self.device)
        noise_pred = self.cfg_guided_model_fn(
            self.model_fn, cfg_scale,
            inputs_shared, inputs_posi, inputs_nega,
            **models, timestep=timestep, progress_id=progress_id
        )
        inputs_shared["latents"] = self.step(self.scheduler, progress_id=progress_id, noise_pred=noise_pred, **inputs_shared)
        
        # Intermediate preview generation
        if preview_callback is not None and (progress_id % preview_interval == 0 or progress_id == num_inference_steps - 1):
            try:
                # Load VAE if VRAM management is active
                if self.vram_management_enabled:
                    self.load_models_to_device(['vae'])
                
                # Decode current latents
                latents_temp = inputs_shared["latents"]
                image_temp = self.vae.decode(latents_temp.unsqueeze(2), device=self.device).squeeze(2)
                image_temp = self.vae_output_to_image(image_temp)
                
                # Restore iteration models if VRAM management is active
                if self.vram_management_enabled:
                    self.load_models_to_device(self.in_iteration_models)
                
                res = preview_callback(image_temp, progress_id, num_inference_steps)
                if res == "CANCEL":
                    raise InterruptedError("Cancelled")
            except InterruptedError:
                raise
            except Exception as e:
                print(f"Error in preview generation callback: {e}")

    # Decode final image
    self.load_models_to_device(['vae'])
    image = self.vae.decode(inputs_shared["latents"].unsqueeze(2), device=self.device).squeeze(2)
    image = self.vae_output_to_image(image)
    self.load_models_to_device([])

    return image

AnimaImagePipeline.__call__ = custom_anima_call


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
    
    # Preview callback settings
    preview_interval = 2
    
    def preview_callback(preview_pil, progress_id, total_steps):
        try:
            preview_path = "data/visual/temp_preview.png"
            preview_pil.save(preview_path)
            if progress_callback:
                try:
                    return progress_callback(progress_id, total_steps, preview_path=preview_path)
                except TypeError:
                    return progress_callback(progress_id, total_steps)
        except Exception as e:
            print(f"Error in preview_callback: {e}")
            
    # Clean up old preview if exists
    preview_file = "data/visual/temp_preview.png"
    if os.path.exists(preview_file):
        try:
            os.remove(preview_file)
        except Exception:
            pass

    def _progress_bar_cmd(iterable, **kwargs):
        """tqdm-compatible wrapper that drives the progress_callback."""
        items = list(iterable)
        total = len(items)
        for i, item in enumerate(items):
            # If this is a preview step, skip calling the progress callback here
            # to let the preview_callback handle the progress update/refresh instead.
            is_preview_step = (i % preview_interval == 0 or i == total - 1)
            if progress_callback and not is_preview_step:
                try:
                    res = progress_callback(i, total)
                    if res == "CANCEL":
                        raise InterruptedError("Cancelled")
                except InterruptedError:
                    raise
                except Exception:
                    pass
            yield item
        if progress_callback:
            try:
                progress_callback(total, total)
            except Exception:
                pass

    try:
        with torch.no_grad():
            image = pipe(
                prompt, 
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                width=width,
                height=height,
                progress_bar_cmd=_progress_bar_cmd,
                preview_callback=preview_callback,
                preview_interval=preview_interval,
            )
    except InterruptedError:
        print("Generation cancelled by user")
        if unload_after:
            del pipe
            unload_pipeline()
        return None
    
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
        del pipe
        unload_pipeline()
    
    return output_path
