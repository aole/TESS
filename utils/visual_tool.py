from nicegui import run

async def generate_image(prompt: str) -> str:
    """
    Generates an image using the Anima diffusion model. This model is specialized in producing high-quality anime-style images and illustrations. It does NOT generate good realistic or photographic images.
    Use this tool when the user asks to generate, create, or draw an image. You must adapt the user's request into a detailed anime-style prompt.

    Args:
        prompt: A detailed description of the image to generate. Ensure it's highly descriptive and includes anime style keywords.
                Example keywords: "masterpiece, best quality, ultra-detailed, anime style, 2d illustration, vibrant colors".
                Example prompt: "masterpiece, best quality, 1girl, solo, magical glowing forest, floating lights, anime style, highly detailed, beautiful eyes".

    Returns:
        The file path to the generated image. You MUST show this image to the user in your markdown response using inline syntax: '![Generated Image](/{path})'
    """

    negative_prompt = "worst quality, low quality, score_1, score_2, score_3, blurry, jpeg artifacts, sepia"
    steps = 30

    try:
        from utils.llm_client import client
        # Unload loaded LLMs to free up VRAM for image generation
        await client.unload_all_models()
    except Exception as e:
        print(f"Warning: Failed to unload LLM: {e}")

    try:
        from services.visual_service import generate_image_task
        print(f"Generating image with prompt: {prompt}")
        output_path = await run.io_bound(generate_image_task, prompt, negative_prompt, steps, 1024, 1024)
        return f"Image successfully generated. Display the image using the following markdown:\n\n![Generated Image](/{output_path})"
    except Exception as e:
        return f"Failed to generate image: {str(e)}"
