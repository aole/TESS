import os
import torch
from core.generate_image import generate_anima_image, get_pipeline, unload_pipeline, flush

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
    import datetime
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
        from PIL import Image
        with Image.open(res_path) as img:
            thumb = img.copy()
            thumb.thumbnail((256, 256))
            thumb_path = os.path.join("data/visual/thumbs", fname)
            thumb.save(thumb_path)
    except Exception as e:
        print(f"Failed to generate thumbnail: {e}")

    return res_path
