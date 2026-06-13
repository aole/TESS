import os
import sys
import torch
import gc
import datetime
import json
import urllib.request
from typing import Optional, Callable, Union

from PIL import Image, ImageFilter, ImageOps
from PIL.PngImagePlugin import PngInfo

# 1. ENVIRONMENT SETUP
# Set model path relative to this script's directory (up one level to root, then /models)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ["DIFFSYNTH_DOWNLOAD_SOURCE"] = "huggingface"
os.environ["DIFFSYNTH_MODEL_BASE_PATH"] = os.path.join(PROJECT_ROOT, "models")

from diffsynth.pipelines.anima_image import AnimaImagePipeline, ModelConfig
from core.anima.lllite import apply_lllite_inpaint


DEFAULT_LLLITE_URL = "https://huggingface.co/kohya-ss/Anima-LLLite/resolve/main/anima-lllite-inpainting-v2.safetensors"
DEFAULT_LLLITE_NAME = "anima-lllite-inpainting-v2.safetensors"


def flush():
    """Aggressive cleanup for small/medium VRAM GPUs."""
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
            tokenizer_config=ModelConfig(
                model_id="circlestone-labs/Anima-Base-v1.0-Diffusers",
                origin_file_pattern="tokenizer/",
            ),
            tokenizer_t5xxl_config=ModelConfig(
                model_id="circlestone-labs/Anima-Base-v1.0-Diffusers",
                origin_file_pattern="t5_tokenizer/",
            ),
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


def _resolve_output_path(output_path: Optional[str], prefix: str = "anima_inpaint") -> str:
    if output_path:
        if os.path.isdir(output_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            return os.path.join(output_path, f"{prefix}_{timestamp}.png").replace("\\", "/")
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        return output_path.replace("\\", "/")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.png"


def _resolve_lllite_path() -> str:
    models_base = os.environ.get(
        "DIFFSYNTH_MODEL_BASE_PATH",
        os.path.abspath(os.path.join(SCRIPT_DIR, "../models")),
    )
    lllite_path = os.path.join(models_base, "loras", DEFAULT_LLLITE_NAME)
    if not os.path.exists(lllite_path):
        os.makedirs(os.path.dirname(lllite_path), exist_ok=True)
        print("Downloading Anima LLLite inpainting weights...")
        urllib.request.urlretrieve(DEFAULT_LLLITE_URL, lllite_path)
    return lllite_path


def _load_and_resize_rgb(image_or_path: Union[str, Image.Image], width: int, height: int, label: str) -> Image.Image:
    if isinstance(image_or_path, str):
        print(f"Loading {label}: {image_or_path}")
        image = Image.open(image_or_path).convert("RGB")
    elif isinstance(image_or_path, Image.Image):
        image = image_or_path.convert("RGB")
    else:
        raise TypeError(f"{label} must be a file path or PIL.Image.Image")

    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return image


def _load_and_resize_inpaint_input(image_or_path: Union[str, Image.Image], width: int, height: int) -> tuple[Image.Image, Image.Image, bool]:
    if isinstance(image_or_path, str):
        print(f"Loading input image: {image_or_path}")
        image = Image.open(image_or_path)
    elif isinstance(image_or_path, Image.Image):
        image = image_or_path
    else:
        raise TypeError("input image must be a file path or PIL.Image.Image")

    has_alpha = image.mode in ("RGBA", "LA") or ("transparency" in image.info)
    rgba_image = image.convert("RGBA") if has_alpha else image.convert("RGB")
    if rgba_image.size != (width, height):
        rgba_image = rgba_image.resize((width, height), Image.Resampling.LANCZOS)

    if not has_alpha:
        rgb_image = rgba_image.convert("RGB")
        return rgb_image, rgb_image, False

    alpha = rgba_image.getchannel("A")
    original_rgb = rgba_image.convert("RGB")
    transparent_mask = ImageOps.invert(alpha)

    noise_channels = [
        Image.effect_noise((width, height), 64).convert("L")
        for _ in range(3)
    ]
    noise_rgb = Image.merge("RGB", noise_channels)
    generation_rgb = Image.composite(noise_rgb, original_rgb, transparent_mask)
    return original_rgb, generation_rgb, bool(transparent_mask.getbbox())


def _make_odd_kernel_size(radius_px: int) -> int:
    """PIL MinFilter/MaxFilter require an odd kernel size >= 3."""
    if radius_px <= 0:
        return 0
    size = radius_px * 2 + 1
    if size < 3:
        size = 3
    if size % 2 == 0:
        size += 1
    return size


def prepare_inpaint_mask(
    mask_image: Union[str, Image.Image],
    width: int,
    height: int,
    mask_blur: int = 16,
    mask_expand: int = 0,
    invert_mask: bool = False,
) -> Image.Image:
    """
    Converts a mask to an L-mode alpha mask.

    Default convention:
      white = editable/generated area
      black = preserved/original area

    Args:
        mask_blur: Gaussian blur radius in pixels. Softens seams.
        mask_expand: Positive values expand white/editable area. Negative values shrink it.
        invert_mask: Use when your source mask uses black=edit and white=preserve.
    """
    if isinstance(mask_image, str):
        print(f"Loading mask image: {mask_image}")
        mask = Image.open(mask_image).convert("L")
    elif isinstance(mask_image, Image.Image):
        mask = mask_image.convert("L")
    else:
        raise TypeError("mask_image must be a file path or PIL.Image.Image")

    if mask.size != (width, height):
        # NEAREST keeps hard mask shapes. Blur can be applied after resize.
        mask = mask.resize((width, height), Image.Resampling.NEAREST)

    if invert_mask:
        mask = ImageOps.invert(mask)

    # Optional grow/shrink of the editable white region.
    if mask_expand != 0:
        kernel_size = _make_odd_kernel_size(abs(mask_expand))
        if kernel_size:
            if mask_expand > 0:
                mask = mask.filter(ImageFilter.MaxFilter(kernel_size))
            else:
                mask = mask.filter(ImageFilter.MinFilter(kernel_size))

    if mask_blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=mask_blur))

    return mask


def apply_turbo_lora(pipe, turbo_lora: float):
    """Loads/clears the official Anima Turbo LoRA if requested."""
    # Enable hot loading to allow clearing LoRA weights dynamically without fusing.
    if hasattr(pipe, "enable_lora_hot_loading"):
        pipe.enable_lora_hot_loading(pipe.dit)

    if hasattr(pipe, "clear_lora"):
        pipe.clear_lora()

    if turbo_lora <= 0.0:
        return

    models_base = os.environ.get(
        "DIFFSYNTH_MODEL_BASE_PATH",
        os.path.abspath(os.path.join(SCRIPT_DIR, "../models")),
    )
    lora_dir = os.path.join(models_base, "loras")
    os.makedirs(lora_dir, exist_ok=True)
    lora_path = os.path.join(lora_dir, "anima-turbo-lora-v0.2.safetensors")

    if not os.path.exists(lora_path):
        print("Downloading Turbo LoRA from Hugging Face...")
        import urllib.request

        url = "https://huggingface.co/circlestone-labs/Anima-Official-LoRAs/resolve/main/anima-turbo-lora-v0.2.safetensors"
        urllib.request.urlretrieve(url, lora_path)
        print("Turbo LoRA downloaded successfully.")

    print(f"Applying Turbo LoRA with strength: {turbo_lora}")
    pipe.load_lora(pipe.dit, lora_path, alpha=turbo_lora)


def _build_progress_bar(progress_callback: Optional[Callable[[int, int], object]] = None):
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

    return _progress_bar_cmd


def _run_img2img_pass(
    pipe,
    prompt: str,
    negative_prompt: str,
    input_image: Image.Image,
    denoising_strength: float,
    steps: int,
    width: int,
    height: int,
    seed: Optional[int],
    cfg_scale: float,
    progress_callback: Optional[Callable[[int, int], object]] = None,
    stage_name: str = "generation",
) -> Image.Image:
    """Runs a DiffSynth Anima img2img pass and normalizes the returned PIL image."""
    if not 0.0 <= denoising_strength <= 1.0:
        raise ValueError(f"{stage_name} denoising_strength must be between 0.0 and 1.0")

    print(
        f"Running {stage_name}: steps={steps}, denoise={denoising_strength:.3f}, "
        f"cfg={cfg_scale}, seed={seed}"
    )

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
            progress_bar_cmd=_build_progress_bar(progress_callback),
        )

    image = image.convert("RGB")
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return image


def generate_anima_inpaint_image(
    prompt: str,
    output_path: str,
    input_image: Union[str, Image.Image],
    mask_image: Union[str, Image.Image],
    negative_prompt: str = "",
    steps: int = 30,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    cfg_scale: float = 4.0,
    progress_callback: Optional[Callable[[int, int], object]] = None,
    unload_after: bool = True,
    vram_limit: Optional[float] = None,
    turbo_lora: float = 0.0,
    denoising_strength: float = 0.65,
    mask_blur: int = 16,
    mask_expand: int = 8,
    invert_mask: bool = False,
    lllite_strength: float = 1.0,
    lllite_start_percent: float = 0.0,
    lllite_end_percent: float = 1.0,
) -> Optional[str]:
    """
    Native Anima LLLite inpainting for DiffSynth Anima.

    Mask convention:
        white = editable/generated area
        black = preserved/original area
    """
    if input_image is None:
        raise ValueError("input_image is required for inpainting")
    if mask_image is None:
        raise ValueError("mask_image is required for inpainting")
    if not 0.0 <= denoising_strength <= 1.0:
        raise ValueError("denoising_strength must be between 0.0 and 1.0")

    orig_input_image_path = input_image if isinstance(input_image, str) else None
    orig_mask_image_path = mask_image if isinstance(mask_image, str) else None

    control_image, generation_input_image, filled_transparency = _load_and_resize_inpaint_input(
        input_image,
        width,
        height,
    )
    raw_mask = prepare_inpaint_mask(
        mask_image,
        width=width,
        height=height,
        mask_blur=0,
        mask_expand=mask_expand,
        invert_mask=invert_mask,
    )
    mask = raw_mask.filter(ImageFilter.GaussianBlur(radius=mask_blur)) if mask_blur > 0 else raw_mask
    lllite_path = _resolve_lllite_path()

    if vram_limit is None:
        if torch.cuda.is_available():
            vram_info = torch.cuda.mem_get_info("cuda")
            vram_limit = vram_info[1] / (1024**3) - 0.5
        else:
            vram_limit = 6.0

    pipe = get_pipeline(vram_limit)
    apply_turbo_lora(pipe, turbo_lora)

    output_path = _resolve_output_path(output_path, prefix="anima_inpaint")

    print(f"Inpainting image: {prompt[:80]}...")
    print("Mask convention: white = generated/editable, black = preserved")
    if filled_transparency:
        print("Transparent input pixels were filled with noise for LLLite conditioning")

    final_image = None
    unpatch_lllite = None
    try:
        unpatch_lllite = apply_lllite_inpaint(
            pipe,
            lllite_path=lllite_path,
            control_image=control_image,
            mask_image=mask,
            strength=lllite_strength,
            start_percent=lllite_start_percent,
            end_percent=lllite_end_percent,
        )
        generated_full = _run_img2img_pass(
            pipe=pipe,
            prompt=prompt,
            negative_prompt=negative_prompt,
            input_image=generation_input_image,
            denoising_strength=denoising_strength,
            steps=steps,
            width=width,
            height=height,
            seed=seed,
            cfg_scale=cfg_scale,
            progress_callback=progress_callback,
            stage_name="LLLite inpaint pass",
        )
        final_image = Image.composite(generated_full, control_image, mask)

    except InterruptedError:
        print("Generation cancelled by user")
        return None
    except Exception as e:
        print(f"Error during inference: {e}")
        raise
    finally:
        if unpatch_lllite is not None:
            unpatch_lllite()
        if unload_after:
            del pipe
            unload_pipeline()

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
        "mode": "anima_lllite_inpaint",
        "denoising_strength": denoising_strength,
        "mask_blur": mask_blur,
        "mask_expand": mask_expand,
        "invert_mask": invert_mask,
        "turbo_lora": turbo_lora,
        "lllite_path": lllite_path,
        "lllite_strength": lllite_strength,
        "lllite_start_percent": lllite_start_percent,
        "lllite_end_percent": lllite_end_percent,
    }
    if orig_input_image_path:
        params["input_image_path"] = orig_input_image_path
    if orig_mask_image_path:
        params["mask_image_path"] = orig_mask_image_path
    metadata.add_text("parameters", json.dumps(params, indent=2))

    final_image.save(output_path, pnginfo=metadata)
    print(f"Success: saved as {output_path}")
    return output_path


# Backward-compatible alias if your app expects a similarly named function.
def generate_anima_image(
    prompt: str,
    output_path: str,
    negative_prompt: str = "",
    steps: int = 30,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    cfg_scale: float = 4.0,
    progress_callback: Optional[Callable[[int, int], object]] = None,
    unload_after: bool = True,
    vram_limit: Optional[float] = None,
    turbo_lora: float = 0.0,
    input_image: Optional[Union[str, Image.Image]] = None,
    mask_image: Optional[Union[str, Image.Image]] = None,
    denoising_strength: float = 0.65,
    mask_blur: int = 16,
    mask_expand: int = 8,
    invert_mask: bool = False,
    lllite_strength: float = 1.0,
    lllite_start_percent: float = 0.0,
    lllite_end_percent: float = 1.0,
) -> Optional[str]:
    if mask_image is None:
        raise ValueError(
            "This inpainting version requires mask_image. "
            "Use the original generate_image.py for plain txt2img/img2img."
        )
    return generate_anima_inpaint_image(
        prompt=prompt,
        output_path=output_path,
        input_image=input_image,
        mask_image=mask_image,
        negative_prompt=negative_prompt,
        steps=steps,
        width=width,
        height=height,
        seed=seed,
        cfg_scale=cfg_scale,
        progress_callback=progress_callback,
        unload_after=unload_after,
        vram_limit=vram_limit,
        turbo_lora=turbo_lora,
        denoising_strength=denoising_strength,
        mask_blur=mask_blur,
        mask_expand=mask_expand,
        invert_mask=invert_mask,
        lllite_strength=lllite_strength,
        lllite_start_percent=lllite_start_percent,
        lllite_end_percent=lllite_end_percent,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Standalone Anima LLLite inpainting generator."
        )
    )
    parser.add_argument("prompt", type=str, help="Prompt for the masked/editable area")
    parser.add_argument("--output", "-o", type=str, default="output_inpaint.png", help="Output path or directory")
    parser.add_argument(
        "--negative-prompt",
        "-n",
        type=str,
        default="worst quality, low quality, score_1, score_2, score_3, artist name, sepia",
        help="Negative prompt",
    )
    parser.add_argument("--steps", "-s", type=int, default=30, help="Number of inference steps")
    parser.add_argument("--width", "-W", type=int, default=1024, help="Output width")
    parser.add_argument("--height", "-H", type=int, default=1024, help="Output height")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed")
    parser.add_argument("--cfg", type=float, default=4.0, help="Classifier-free guidance scale")
    parser.add_argument("--vram-limit", type=float, default=None, help="VRAM limit in GB")
    parser.add_argument("--turbo-lora", type=float, default=0.0, help="Strength of the Turbo LoRA; 0 disables it")
    parser.add_argument("--input-image", "-i", type=str, required=True, help="Original image path")
    parser.add_argument("--mask-image", "-m", type=str, required=True, help="Mask image path. White edits, black preserves.")
    parser.add_argument(
        "--denoising-strength",
        "-d",
        type=float,
        default=0.65,
        help="Img2img denoising strength, 0.0 to 1.0. Higher changes more.",
    )
    parser.add_argument("--mask-blur", type=int, default=16, help="Gaussian blur radius for mask edge blending")
    parser.add_argument("--mask-expand", type=int, default=8, help="Expand editable white region in pixels; negative shrinks")
    parser.add_argument("--invert-mask", action="store_true", help="Use when your mask is black=edit and white=preserve")
    parser.add_argument("--lllite-strength", type=float, default=1.0, help="LLLite conditioning strength")
    parser.add_argument("--lllite-start-percent", type=float, default=0.0, help="First denoise percent to apply LLLite")
    parser.add_argument("--lllite-end-percent", type=float, default=1.0, help="Last denoise percent to apply LLLite")

    args = parser.parse_args()

    try:
        generate_anima_inpaint_image(
            prompt=args.prompt,
            output_path=args.output,
            input_image=args.input_image,
            mask_image=args.mask_image,
            negative_prompt=args.negative_prompt,
            steps=args.steps,
            width=args.width,
            height=args.height,
            seed=args.seed,
            cfg_scale=args.cfg,
            vram_limit=args.vram_limit,
            turbo_lora=args.turbo_lora,
            unload_after=True,
            denoising_strength=args.denoising_strength,
            mask_blur=args.mask_blur,
            mask_expand=args.mask_expand,
            invert_mask=args.invert_mask,
            lllite_strength=args.lllite_strength,
            lllite_start_percent=args.lllite_start_percent,
            lllite_end_percent=args.lllite_end_percent,
        )
    except Exception as e:
        print(f"Failed to generate image: {e}")
        sys.exit(1)
