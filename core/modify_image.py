import os
import sys
import gc
import json
import datetime
import io
from PIL import Image
from PIL.PngImagePlugin import PngInfo

_cached_session = None
_cached_model = None

def get_session(model_name: str):
    global _cached_session, _cached_model
    if _cached_session is None or _cached_model != model_name:
        print(f"--- Initializing rembg session with model {model_name} ---")
        from rembg import new_session
        _cached_session = new_session(model_name)
        _cached_model = model_name
    return _cached_session

def unload_session():
    global _cached_session, _cached_model
    if _cached_session is not None:
        print("Unloading rembg session...")
        _cached_session = None
        _cached_model = None
    gc.collect()

def image_text_metadata(fpath: str) -> dict:
    try:
        with Image.open(fpath) as img:
            metadata = img.text if hasattr(img, 'text') else img.info
            return {
                key: value for key, value in metadata.items()
                if isinstance(key, str) and isinstance(value, str)
            }
    except Exception:
        return {}

def tool_png_metadata(source_path: str, tool_meta: dict) -> PngInfo:
    source_metadata = image_text_metadata(source_path)
    metadata = PngInfo()

    for key, value in source_metadata.items():
        metadata.add_text(key, value)

    existing_tools = []
    if source_metadata.get('tools'):
        try:
            parsed_tools = json.loads(source_metadata['tools'])
            if isinstance(parsed_tools, list):
                existing_tools = parsed_tools
        except Exception:
            existing_tools = []

    metadata.add_text('source_image', source_path.replace('\\', '/'))
    metadata.add_text('source_metadata', json.dumps(source_metadata, indent=2))
    metadata.add_text('tools', json.dumps([*existing_tools, tool_meta], indent=2))
    return metadata

def modify_image(
    input_path: str,
    output_path: str,
    operation: str = "remove_background",
    model_name: str = "isnet-anime",
    unload_after: bool = True,
) -> str:
    """
    Modifies an image (e.g. background removal) and saves it to the output path.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input image not found: {input_path}")

    # Output path handling
    if output_path:
        if os.path.isdir(output_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_path, f"modified_{timestamp}.png").replace('\\', '/')
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            output_path = output_path.replace('\\', '/')
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"modified_{timestamp}.png"

    if operation == "remove_background":
        from rembg import remove
        session = get_session(model_name)
        
        print(f"Removing background from {input_path} using model {model_name}...")
        with open(input_path, 'rb') as input_file:
            input_bytes = input_file.read()
        output_bytes = remove(input_bytes, session=session)
        
        tool_meta = {
            'name': 'remove_background',
            'model': model_name,
            'source_image': input_path.replace('\\', '/'),
            'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
        }
        metadata = tool_png_metadata(input_path, tool_meta)
        
        with Image.open(io.BytesIO(output_bytes)) as img:
            img.save(output_path, pnginfo=metadata)
            
        print(f"Background removed successfully, saved to {output_path}")
    else:
        raise ValueError(f"Unknown operation: {operation}")

    if unload_after:
        unload_session()
        
    return output_path

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Standalone Image Modifier")
    parser.add_argument("input", type=str, help="Path to input image")
    parser.add_argument("--output", "-o", type=str, default="output.png", help="Output path (filename or directory)")
    parser.add_argument("--operation", type=str, default="remove_background", choices=["remove_background"], help="Modification operation to perform")
    parser.add_argument("--model", type=str, default="isnet-anime", help="Model name for background removal")
    parser.add_argument("--no-unload", dest="unload_after", action="store_false", help="Do not unload model session after modification")
    
    args = parser.parse_args()
    
    try:
        modify_image(
            input_path=args.input,
            output_path=args.output,
            operation=args.operation,
            model_name=args.model,
            unload_after=args.unload_after,
        )
    except Exception as e:
        print(f"Failed to modify image: {e}")
        sys.exit(1)
