"""
Standalone Real-ESRGAN anime image upscaler.

Uses:
    RealESRGAN_x4plus_anime_6B

Examples:
    python core/upscale_image.py input.png
    python core/upscale_image.py input1.png input2.jpg -o outputs
    python core/upscale_image.py images_folder -o outputs --recursive
    python core/upscale_image.py images_folder -o outputs --outscale 2
    python core/upscale_image.py input.png --tile 256

Notes:
    - This model internally upscales by 4x.
    - --outscale can resize the final result to 2x, 3x, 4x, etc.
    - Use --tile 256 or --tile 512 if you hit VRAM issues.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path
from typing import Iterable

import cv2
import torch
from tqdm import tqdm

from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer


MODEL_NAME = "RealESRGAN_x4plus_anime_6B"
MODEL_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/"
    "v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"
)

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size > 0:
        return

    print(f"Downloading model weights to: {dest}")
    urllib.request.urlretrieve(url, dest)


def find_images(paths: list[Path], recursive: bool) -> list[Path]:
    images: list[Path] = []

    for path in paths:
        if path.is_file():
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(path)
            else:
                print(f"Skipping unsupported file: {path}")
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            for item in path.glob(pattern):
                if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
                    images.append(item)
        else:
            print(f"Path does not exist: {path}")

    return sorted(set(images))


def build_output_path(
    input_path: Path,
    output_dir: Path,
    suffix: str,
    ext: str,
    overwrite: bool,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    if ext == "auto":
        output_ext = input_path.suffix.lower()
    else:
        output_ext = f".{ext.lower().lstrip('.')}"

    output_path = output_dir / f"{input_path.stem}{suffix}{output_ext}"

    if overwrite:
        return output_path

    if not output_path.exists():
        return output_path

    counter = 2
    while True:
        candidate = output_dir / f"{input_path.stem}{suffix}_{counter}{output_ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def create_upsampler(
    model_path: Path,
    tile: int,
    tile_pad: int,
    pre_pad: int,
    fp32: bool,
    gpu_id: int | None,
) -> RealESRGANer:
    # RealESRGAN_x4plus_anime_6B uses a smaller 6-block RRDBNet.
    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=6,
        num_grow_ch=32,
        scale=4,
    )

    use_half = torch.cuda.is_available() and not fp32

    return RealESRGANer(
        scale=4,
        model_path=str(model_path),
        model=model,
        tile=tile,
        tile_pad=tile_pad,
        pre_pad=pre_pad,
        half=use_half,
        gpu_id=gpu_id,
    )


def upscale_image(
    upsampler: RealESRGANer,
    input_path: Path,
    output_path: Path,
    outscale: float,
    alpha_upsampler: str,
) -> bool:
    img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)

    if img is None:
        print(f"Failed to read image: {input_path}")
        return False

    try:
        output, _ = upsampler.enhance(
            img,
            outscale=outscale,
            alpha_upsampler=alpha_upsampler,
        )
    except RuntimeError as exc:
        message = str(exc).lower()

        if "out of memory" in message or "cuda" in message:
            print(f"CUDA/VRAM error while processing: {input_path}")
            print("Try again with --tile 256 or --tile 128.")
        else:
            print(f"Runtime error while processing {input_path}: {exc}")

        return False
    except Exception as exc:
        print(f"Failed to upscale {input_path}: {exc}")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    success = cv2.imwrite(str(output_path), output)

    if not success:
        print(f"Failed to save image: {output_path}")
        return False

    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upscale one or more images using RealESRGAN_x4plus_anime_6B."
    )

    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input image file(s) or folder(s).",
    )

    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("outputs/upscaled"),
        help="Output folder. Default: outputs/upscaled",
    )

    parser.add_argument(
        "--weights-dir",
        type=Path,
        default=Path("models/realesrgan"),
        help="Folder for model weights. Default: models/realesrgan",
    )

    parser.add_argument(
        "--outscale",
        type=float,
        default=4.0,
        help="Final output scale. Default: 4. Use 2 for 2x output.",
    )

    parser.add_argument(
        "--suffix",
        default="_realesrgan_x4_anime",
        help="Filename suffix for output images.",
    )

    parser.add_argument(
        "--ext",
        choices=["auto", "png", "jpg", "jpeg", "webp"],
        default="auto",
        help="Output extension. Default: auto.",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search folders recursively.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output files if they already exist.",
    )

    parser.add_argument(
        "--tile",
        type=int,
        default=0,
        help=(
            "Tile size. 0 means no tiling. "
            "Use 256 or 512 if you run out of VRAM."
        ),
    )

    parser.add_argument(
        "--tile-pad",
        type=int,
        default=10,
        help="Tile padding. Default: 10.",
    )

    parser.add_argument(
        "--pre-pad",
        type=int,
        default=10,
        help="Pre padding. Default: 10.",
    )

    parser.add_argument(
        "--fp32",
        action="store_true",
        help="Use fp32 instead of fp16. Slower but sometimes safer.",
    )

    parser.add_argument(
        "--gpu-id",
        type=int,
        default=None,
        help="GPU id to use. Default: auto.",
    )

    parser.add_argument(
        "--alpha-upsampler",
        choices=["realesrgan", "cv2"],
        default="realesrgan",
        help=(
            "How to upscale alpha channel for transparent images. "
            "Default: realesrgan. Use cv2 if transparent edges look weird."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    model_path = args.weights_dir / f"{MODEL_NAME}.pth"
    download_file(MODEL_URL, model_path)

    images = find_images(args.inputs, args.recursive)

    if not images:
        print("No supported images found.")
        return 1

    device_name = "CUDA" if torch.cuda.is_available() else "CPU"
    print(f"Device: {device_name}")
    print(f"Model: {MODEL_NAME}")
    print(f"Images found: {len(images)}")

    if not torch.cuda.is_available():
        print("Warning: CUDA not available. This will be slow on CPU.")

    upsampler = create_upsampler(
        model_path=model_path,
        tile=args.tile,
        tile_pad=args.tile_pad,
        pre_pad=args.pre_pad,
        fp32=args.fp32,
        gpu_id=args.gpu_id,
    )

    success_count = 0

    for input_path in tqdm(images, desc="Upscaling"):
        output_path = build_output_path(
            input_path=input_path,
            output_dir=args.output_dir,
            suffix=args.suffix,
            ext=args.ext,
            overwrite=args.overwrite,
        )

        ok = upscale_image(
            upsampler=upsampler,
            input_path=input_path,
            output_path=output_path,
            outscale=args.outscale,
            alpha_upsampler=args.alpha_upsampler,
        )

        if ok:
            success_count += 1
            tqdm.write(f"Saved: {output_path}")

    print(f"Done. Upscaled {success_count}/{len(images)} image(s).")

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
    