import os
import sys
import time
import torch
import gc
import datetime
import json
from PIL.PngImagePlugin import PngInfo

# 1. ENVIRONMENT SETUP
# Set model path relative to this script's directory (up one level to root, then /models)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["DIFFSYNTH_DOWNLOAD_SOURCE"] = "huggingface"
os.environ["DIFFSYNTH_MODEL_BASE_PATH"] = os.path.abspath(os.path.join(SCRIPT_DIR, "../models"))

from diffsynth.pipelines.anima_image import AnimaImagePipeline, ModelConfig

def flush():
    """Nuclear cleanup for 8GB VRAM."""
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    gc.collect()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

_cached_pipe = None



def get_pipeline(vram_limit: float):
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
            tokenizer_config=ModelConfig(model_id="circlestone-labs/Anima-Base-v1.0-Diffusers", origin_file_pattern="tokenizer/"),
            tokenizer_t5xxl_config=ModelConfig(model_id="circlestone-labs/Anima-Base-v1.0-Diffusers", origin_file_pattern="t5_tokenizer/"),
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


def generate_anima_image(
    prompt: str,
    output_path: str,
    negative_prompt: str = "",
    steps: int = 30,
    width: int = 1024,
    height: int = 1024,
    seed: int = None,
    cfg_scale: float = 4.0,
    progress_callback = None,
    unload_after: bool = True,
    vram_limit: float = None,
    turbo_lora: float = 0.0,
    input_image = None,
    denoising_strength: float = 1.0,
) -> str:
    """
    Generates an image using the Anima diffusion model and saves it to the output path.
    """
    orig_input_image_path = input_image if isinstance(input_image, str) else None
    opened_input_image = None
    if input_image is not None:
        from PIL import Image
        if isinstance(input_image, str):
            print(f"Loading input image: {input_image}")
            opened_input_image = Image.open(input_image)
            input_image = opened_input_image.convert("RGB")
        input_image = input_image.resize((width, height), Image.Resampling.LANCZOS)
    if vram_limit is None:
        if torch.cuda.is_available():
            vram_info = torch.cuda.mem_get_info("cuda")
            vram_limit = vram_info[1] / (1024 ** 3) - 0.5
        else:
            vram_limit = 6.0

    pipe = get_pipeline(vram_limit)

    # Reused img2img runs on low-VRAM GPUs benefit from clearing stale cached blocks
    # before the next inference begins.
    if input_image is not None and not unload_after:
        flush()

    # Enable hot loading to allow clearing LoRA weights dynamically without fusing
    if hasattr(pipe, "enable_lora_hot_loading"):
        pipe.enable_lora_hot_loading(pipe.dit)

    # Manage Turbo LoRA
    if hasattr(pipe, "clear_lora"):
        pipe.clear_lora()

    if turbo_lora > 0.0:
        models_base = os.environ.get("DIFFSYNTH_MODEL_BASE_PATH", os.path.abspath(os.path.join(SCRIPT_DIR, "../models")))
        lora_dir = os.path.join(models_base, "loras")
        os.makedirs(lora_dir, exist_ok=True)
        lora_path = os.path.join(lora_dir, "anima-turbo-lora-v0.2.safetensors")

        if not os.path.exists(lora_path):
            print(f"Downloading Turbo LoRA from Hugging Face...")
            import urllib.request
            url = "https://huggingface.co/circlestone-labs/Anima-Official-LoRAs/resolve/main/anima-turbo-lora-v0.2.safetensors"
            urllib.request.urlretrieve(url, lora_path)
            print("Turbo LoRA downloaded successfully.")

        print(f"Applying Turbo LoRA with strength: {turbo_lora}")
        pipe.load_lora(pipe.dit, lora_path, alpha=turbo_lora)

    print(f"Generating image: {prompt[:50]}...")
    
    def _progress_bar_cmd(iterable, **kwargs):
        from tqdm import tqdm
        items = list(iterable)
        total = len(items)
        if progress_callback:
            for i, item in enumerate(items):
                try:
                    res = progress_callback(i, total)
                    if res == "CANCEL":
                        raise InterruptedError("Cancelled")
                except InterruptedError:
                    raise
                except Exception:
                    pass
                yield item
            try:
                progress_callback(total, total)
            except Exception:
                pass
        else:
            for item in tqdm(items, desc="Generating", **kwargs):
                yield item

    image = None
    try:
        with torch.no_grad():
            image = pipe(
                prompt,
                negative_prompt=negative_prompt,
                input_image=input_image,
                denoising_strength=denoising_strength,
                num_inference_steps=steps,
                width=width,
                height=height,
                seed=seed,
                cfg_scale=cfg_scale,
                progress_bar_cmd=_progress_bar_cmd,
            )
    except InterruptedError:
        print("Generation cancelled by user")
        return None
    except Exception as e:
        print(f"Error during inference: {e}")
        raise e
    finally:
        if opened_input_image is not None:
            opened_input_image.close()
        if unload_after:
            del pipe
            unload_pipeline()

    # Handle output path
    if output_path:
        if os.path.isdir(output_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_path, f"anima_{timestamp}.png").replace('\\', '/')
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            output_path = output_path.replace('\\', '/')
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"anima_{timestamp}.png"

    # Add PNG metadata
    metadata = PngInfo()
    params = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "width": width,
        "height": height,
        "seed": seed,
        "cfg_scale": cfg_scale,
        "model": "Anima Base v1.0",
        "turbo_lora": turbo_lora
    }
    if input_image is not None:
        params["denoising_strength"] = denoising_strength
        if orig_input_image_path:
            params["input_image_path"] = orig_input_image_path
    metadata.add_text("parameters", json.dumps(params, indent=2))
    
    # Save the generated image
    image.save(output_path, pnginfo=metadata)
    print(f"Success: saved as {output_path}")

    # Release per-image allocations before the next batch item reuses the pipeline.
    del image
    if input_image is not None and not unload_after:
        flush()
        
    return output_path


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Standalone Anima Image Generator")
    parser.add_argument("prompt", type=str, help="Prompt for image generation")
    parser.add_argument("--output", "-o", type=str, default="output.png", help="Output path (filename or directory)")
    parser.add_argument("--negative-prompt", "-n", type=str, default="worst quality, low quality, score_1, score_2, score_3, artist name, sepia", help="Negative prompt")
    parser.add_argument("--steps", "-s", type=int, default=30, help="Number of inference steps")
    parser.add_argument("--width", "-W", type=int, default=1024, help="Width of the generated image")
    parser.add_argument("--height", "-H", type=int, default=1024, help="Height of the generated image")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed for generation")
    parser.add_argument("--cfg", type=float, default=4.0, help="Classifier free guidance scale (CFG)")
    parser.add_argument("--vram-limit", type=float, default=None, help="VRAM limit in GB")
    parser.add_argument("--turbo-lora", type=float, default=0.0, help="Strength of the Turbo LoRA (0.0 to disable)")
    parser.add_argument("--input-image", "-i", type=str, default=None, help="Optional input image path for image-to-image (itoi) generation")
    parser.add_argument("--denoising-strength", "-d", type=float, default=1.0, help="Denoising strength for image-to-image generation (0.0 to 1.0)")
    
    args = parser.parse_args()
    
    try:
        generate_anima_image(
            prompt=args.prompt,
            output_path=args.output,
            negative_prompt=args.negative_prompt,
            steps=args.steps,
            width=args.width,
            height=args.height,
            seed=args.seed,
            cfg_scale=args.cfg,
            vram_limit=args.vram_limit,
            turbo_lora=args.turbo_lora,
            unload_after=True,
            input_image=args.input_image,
            denoising_strength=args.denoising_strength,
        )
    except Exception as e:
        print(f"Failed to generate image: {e}")
        sys.exit(1)
