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
