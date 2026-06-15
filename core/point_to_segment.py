import argparse
import os
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MODELS_DIR = PROJECT_ROOT / "models"
HF_CACHE_DIR = MODELS_DIR / "huggingface"

os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))
os.environ.setdefault("HF_HUB_CACHE", str(HF_CACHE_DIR / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_CACHE_DIR / "transformers"))
HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

import numpy as np
import torch
from PIL import Image

from sam2.sam2_image_predictor import SAM2ImagePredictor


DEFAULT_SAM_MODEL = "facebook/sam2.1-hiera-large"


def load_image(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")


def save_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255).save(path)


def save_overlay(
    image: Image.Image,
    mask: np.ndarray,
    points: np.ndarray,
    labels: np.ndarray,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    base = np.array(image).astype(np.float32)
    overlay = base.copy()

    mask_bool = mask.astype(bool)
    overlay[mask_bool] = overlay[mask_bool] * 0.45 + np.array([255, 0, 0]) * 0.55

    for (x, y), label in zip(points, labels):
        x, y = int(x), int(y)
        x1, x2 = max(0, x - 3), min(base.shape[1], x + 4)
        y1, y2 = max(0, y - 3), min(base.shape[0], y + 4)

        if label == 1:
            overlay[y1:y2, x1:x2] = np.array([0, 255, 0])
        else:
            overlay[y1:y2, x1:x2] = np.array([0, 0, 255])

    Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8)).save(path)


def parse_points(points_str: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse points formatted as "x,y,label;x,y,label"."""
    points: list[list[float]] = []
    labels: list[int] = []

    for item in points_str.split(";"):
        item = item.strip()
        if not item:
            continue

        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 3:
            raise ValueError(f'Invalid point "{item}". Expected "x,y,label".')

        x, y, label = parts
        label_int = int(label)
        if label_int not in (0, 1):
            raise ValueError(f'Invalid label "{label}" for point "{item}". Use 1=foreground or 0=background.')

        points.append([float(x), float(y)])
        labels.append(label_int)

    if not points:
        raise ValueError('At least one point is required. Example: "320,240,1;100,100,0".')

    return np.array(points, dtype=np.float32), np.array(labels, dtype=np.int32)


def segment_from_points(
    image_path: str,
    points: np.ndarray,
    labels: np.ndarray,
    out_dir: str | Path = "sam21_point_output",
    sam_model: str = DEFAULT_SAM_MODEL,
) -> tuple[Path, Path, int, float]:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    image = load_image(image_path)
    image_np = np.array(image)

    predictor = SAM2ImagePredictor.from_pretrained(sam_model, device=device)
    predictor.set_image(image_np)

    with torch.no_grad():
        masks, scores, _ = predictor.predict(
            point_coords=points,
            point_labels=labels,
            multimask_output=True,
        )

    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    best_mask = masks[best_idx]

    mask_path = out_path / "mask.png"
    overlay_path = out_path / "overlay.png"
    save_mask(best_mask, mask_path)
    save_overlay(image, best_mask, points, labels, overlay_path)

    return mask_path, overlay_path, best_idx, best_score


def main() -> None:
    parser = argparse.ArgumentParser(description="Segment an image from foreground/background points with SAM 2.1.")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument(
        "--points",
        required=True,
        help='Points as "x,y,label;x,y,label" where label is 1=foreground, 0=background',
    )
    parser.add_argument("--out", default="sam21_point_output", help="Output folder")
    parser.add_argument("--sam-model", default=DEFAULT_SAM_MODEL, help="SAM 2.1 Hugging Face model id")
    args = parser.parse_args()

    points, labels = parse_points(args.points)
    mask_path, overlay_path, best_idx, best_score = segment_from_points(
        image_path=args.image,
        points=points,
        labels=labels,
        out_dir=args.out,
        sam_model=args.sam_model,
    )

    print(f"Device: {'cuda' if torch.cuda.is_available() else 'cpu'}")
    print(f"Model cache: {HF_CACHE_DIR}")
    print(f"Best mask index: {best_idx}")
    print(f"Best score: {best_score:.4f}")
    print(f"Saved mask: {mask_path}")
    print(f"Saved overlay: {overlay_path}")


if __name__ == "__main__":
    main()
