import os
import torch
import gc
from PIL import Image

# 1. ENVIRONMENT SETUP
os.environ["DIFFSYNTH_DOWNLOAD_SOURCE"] = "huggingface"
# Force the library to use a clean local directory
os.environ["DIFFSYNTH_MODEL_BASE_PATH"] = os.path.abspath("./models")

from diffsynth.pipelines.anima_image import AnimaImagePipeline, ModelConfig

def flush():
    """Nuclear cleanup for 8GB VRAM."""
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    gc.collect()
    torch.cuda.empty_cache()

def generate():
    # Calculate VRAM limit for an 8GB card (leaving a small buffer)
    vram_limit = torch.cuda.mem_get_info("cuda")[1] / (1024 ** 3) - 0.5
    print(f"--- Initializing Anima Preview 3 on {vram_limit:.2f}GB VRAM ---")

    # 2. PIPELINE INITIALIZATION
    # We MUST use the 'split_files/' prefix to match the Hugging Face repo structure
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
        # Only use the lightweight Qwen tokenizer
        tokenizer_config=ModelConfig(model_id="Qwen/Qwen3-0.6B", origin_file_pattern="./"),
        tokenizer_t5xxl_config=ModelConfig(model_id="aoleb/t5-v1_1-xxl-tokenizer", origin_file_pattern="./"),
        vram_limit=vram_limit,
    )

    # 3. INFERENCE
    # Anima requires 'score_9' for high-quality results
    prompt = "masterpiece, best quality, score_7, safe, 1boy, wizard robes, holding a staff, swirling nebula energy, constellations in hair, dark forest, mystical lighting, cinematic rim light"
    negative_prompt = "worst quality, low quality, score_1, score_2, score_3, artist name, nsfw"

    print("Generating image...")
    with torch.no_grad():
        image = pipe(
            prompt, 
            negative_prompt=negative_prompt,
            # seed=0, 
            num_inference_steps=30, # Preview 3 is optimized for 30-50 steps
            width=1024,
            height=1024
        )
    
    image.save("anima_preview3_final.png")
    print("Success: saved as anima_preview3_final.png")

if __name__ == "__main__":
    try:
        generate()
    finally:
        flush()
