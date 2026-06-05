import os
import sys
import datetime
import json
from PIL import Image
from PIL.PngImagePlugin import PngInfo

def create_image(
    output_path: str,
    rgb,
    width: int = 1024,
    height: int = 1024,
) -> str:
    """
    Creates a plain image with the specified background color (RGB) and size, and saves it.
    """
    # Parse and validate RGB parameter
    if isinstance(rgb, str):
        rgb_str = rgb.strip()
        if rgb_str.startswith("#"):
            rgb_str = rgb_str.lstrip('#')
            if len(rgb_str) == 6:
                rgb = tuple(int(rgb_str[i:i+2], 16) for i in (0, 2, 4))
            elif len(rgb_str) == 3:
                rgb = tuple(int(c * 2, 16) for c in rgb_str)
            else:
                raise ValueError(f"Invalid hex color length: #{rgb_str}")
        else:
            if rgb_str.lower().startswith("rgb"):
                rgb_str = rgb_str[3:].strip("() ")
            try:
                parts = [int(p.strip()) for p in rgb_str.split(",")]
            except ValueError as e:
                raise ValueError(f"RGB values must be integers. Details: {e}")
            if len(parts) != 3:
                raise ValueError(f"RGB string must have 3 comma-separated components: {rgb}")
            rgb = tuple(parts)
    elif isinstance(rgb, (list, tuple)):
        if len(rgb) != 3:
            raise ValueError(f"RGB tuple/list must have exactly 3 components: {rgb}")
        rgb = tuple(int(x) for x in rgb)
    else:
        raise TypeError(f"RGB must be a tuple, list, or comma-separated string, got {type(rgb)}")

    for val in rgb:
        if not (0 <= val <= 255):
            raise ValueError(f"RGB values must be between 0 and 255, got: {rgb}")

    # Output path handling
    if output_path:
        if os.path.isdir(output_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_path, f"created_{timestamp}.png").replace('\\', '/')
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            output_path = output_path.replace('\\', '/')
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"created_{timestamp}.png"

    print(f"Creating plain image of size {width}x{height} with background RGB {rgb}...")

    # Create the plain image
    img = Image.new("RGB", (width, height), color=rgb)

    # Add PNG metadata
    metadata = PngInfo()
    params = {
        "type": "plain_color",
        "rgb": list(rgb),
        "width": width,
        "height": height,
        "created_at": datetime.datetime.now().isoformat(timespec='seconds'),
    }
    metadata.add_text("parameters", json.dumps(params, indent=2))

    img.save(output_path, pnginfo=metadata)
    print(f"Plain image created successfully, saved to {output_path}")
    return output_path

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Standalone Plain Image Creator")
    parser.add_argument("--output", "-o", type=str, default="output.png", help="Output path (filename or directory)")
    parser.add_argument("--rgb", type=str, default="255,255,255", help="RGB background color as comma-separated values (e.g. 255,0,0)")
    parser.add_argument("--width", "-W", type=int, default=1024, help="Width of the generated image")
    parser.add_argument("--height", "-H", type=int, default=1024, help="Height of the generated image")

    args = parser.parse_args()

    try:
        create_image(
            output_path=args.output,
            rgb=args.rgb,
            width=args.width,
            height=args.height,
        )
    except Exception as e:
        print(f"Failed to create image: {e}")
        sys.exit(1)
