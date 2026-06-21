import datetime
import io
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from core.config.settings_service import settings_service
from core.db.connection import get_connection


CACHE_DIR = Path("data/visual/temp/db_cache")
DB_PATH_RE = re.compile(r"^data/visual/temp/db_cache/db_(\d+)_")


def _json_or_none(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _image_metadata(path: str) -> dict[str, Any]:
    with Image.open(path) as img:
        source = img.text if hasattr(img, "text") else img.info
        raw = {key: value for key, value in dict(source).items() if isinstance(value, str)}
    params = _json_or_none(raw.get("parameters")) or {}
    return {
        "parameters": params,
        "png_text": raw,
    }


def _thumbnail_bytes(path: str) -> tuple[bytes, str, int, int]:
    thumb_fmt = settings_service.get("thumbnail_format", "webp")
    thumb_size = int(settings_service.get("thumbnail_size", 256))
    output_format = "JPEG" if thumb_fmt == "jpg" else thumb_fmt.upper()
    mime_type = "image/jpeg" if thumb_fmt == "jpg" else f"image/{thumb_fmt}"
    with Image.open(path) as img:
        thumb = ImageOps.fit(img, (thumb_size, thumb_size), method=Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        thumb.save(buffer, format=output_format, quality=80, optimize=True)
    return buffer.getvalue(), mime_type, thumb_size, thumb_size


def _configured_limit_bytes() -> int:
    return int(settings_service.get("visual_db_max_size_mb", 100)) * 1024 * 1024


def _storage_bytes(conn) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(LENGTH(image_data)), 0) + COALESCE(SUM(LENGTH(thumbnail_data)), 0) AS total
        FROM visual_images
        WHERE deleted_at IS NULL
        """
    ).fetchone()
    return int(row["total"] or 0)


def _cache_name(image_id: int, filename: str | None) -> Path:
    safe_name = "".join(c for c in (filename or f"image_{image_id}.png") if c.isalnum() or c in "._-")
    return CACHE_DIR / f"db_{image_id}_{safe_name}"


def db_id_from_path(path: str | None) -> int | None:
    if not path:
        return None
    match = DB_PATH_RE.match(path.replace("\\", "/").lstrip("/"))
    return int(match.group(1)) if match else None


# Store durable image bytes and thumbnail bytes in a single visual_images row.
def save_image_file(path: str, operation: str, *, comment: str | None = None) -> str:
    metadata = _image_metadata(path)
    params = metadata.get("parameters") or {}
    with Image.open(path) as img:
        width, height = img.size
        image_format = (img.format or Path(path).suffix.lstrip(".") or "png").lower()

    image_bytes = Path(path).read_bytes()
    thumb_bytes, thumb_mime, thumb_w, thumb_h = _thumbnail_bytes(path)
    new_bytes = len(image_bytes) + len(thumb_bytes)
    mime_type = mimetypes.guess_type(path)[0] or f"image/{image_format}"
    filename = os.path.basename(path)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        if _storage_bytes(conn) + new_bytes > _configured_limit_bytes():
            raise RuntimeError("Visual image database size limit would be exceeded.")
        cur = conn.execute(
            """
            INSERT INTO visual_images (
                original_filename, mime_type, width, height, file_size, image_data,
                thumbnail_data, thumbnail_mime_type, thumbnail_width, thumbnail_height,
                thumbnail_generated_at, prompt, negative_prompt, seed, model, steps,
                cfg_scale, denoising, turbo_lora, generation_mode, operation,
                input_image_path, mask_image_path, comment, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                filename,
                mime_type,
                width,
                height,
                len(image_bytes),
                image_bytes,
                thumb_bytes,
                thumb_mime,
                thumb_w,
                thumb_h,
                now,
                params.get("prompt"),
                params.get("negative_prompt"),
                params.get("seed"),
                params.get("model"),
                params.get("steps"),
                params.get("cfg_scale"),
                params.get("denoising_strength"),
                params.get("turbo_lora"),
                params.get("generation_mode") or params.get("mode"),
                operation,
                params.get("input_image_path"),
                params.get("mask_image_path"),
                comment,
                json.dumps(metadata),
            ),
        )
        image_id = int(cur.lastrowid)
        conn.commit()

    return materialize_image(image_id)


# Materialize DB bytes as disposable cache files for PIL, Photopea, and downloads.
def materialize_image(image_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT original_filename, image_data FROM visual_images WHERE id = ? AND deleted_at IS NULL",
            (image_id,),
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"Visual image {image_id} was not found.")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_name(image_id, row["original_filename"])
    cache_path.write_bytes(row["image_data"])
    return str(cache_path).replace("\\", "/")


def materialize_path(path: str) -> str:
    image_id = db_id_from_path(path)
    return materialize_image(image_id) if image_id else path


def list_images(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    where = ["deleted_at IS NULL"]
    if not include_hidden:
        where.append("hidden = 0")
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, original_filename, width, height, hidden, operation, created_at
            FROM visual_images
            WHERE {" AND ".join(where)}
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "filename": row["original_filename"] or f"image_{row['id']}.png",
            "path": materialize_image(row["id"]),
            "thumb": f"/visual-db/thumb/{row['id']}",
            "width": row["width"],
            "height": row["height"],
            "hidden": bool(row["hidden"]),
            "operation": row["operation"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_metadata(path: str) -> dict[str, Any] | None:
    image_id = db_id_from_path(path)
    if not image_id:
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT metadata_json FROM visual_images WHERE id = ?", (image_id,)).fetchone()
    metadata = _json_or_none(row["metadata_json"] if row else None) or {}
    return metadata.get("parameters") or None


def set_hidden(path: str, hidden: bool) -> None:
    image_id = db_id_from_path(path)
    if not image_id:
        return
    with get_connection() as conn:
        conn.execute(
            "UPDATE visual_images SET hidden = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if hidden else 0, image_id),
        )
        conn.commit()


def is_hidden(path: str) -> bool:
    image_id = db_id_from_path(path)
    if not image_id:
        return False
    with get_connection() as conn:
        row = conn.execute("SELECT hidden FROM visual_images WHERE id = ?", (image_id,)).fetchone()
    return bool(row and row["hidden"])


def soft_delete(path: str) -> None:
    image_id = db_id_from_path(path)
    if not image_id:
        return
    with get_connection() as conn:
        conn.execute(
            "UPDATE visual_images SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (image_id,),
        )
        conn.commit()


def purge_expired_deleted() -> None:
    days = int(settings_service.get("visual_deleted_retention_days", 30))
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM visual_images WHERE deleted_at IS NOT NULL AND deleted_at <= datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()


def thumbnail_response(image_id: int) -> tuple[bytes, str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT thumbnail_data, thumbnail_mime_type FROM visual_images WHERE id = ? AND deleted_at IS NULL",
            (image_id,),
        ).fetchone()
    if row is None or row["thumbnail_data"] is None:
        raise FileNotFoundError(f"Thumbnail for visual image {image_id} was not found.")
    return row["thumbnail_data"], row["thumbnail_mime_type"] or "image/webp"


# Rebuild thumbnail columns in-place after thumbnail settings change.
def regenerate_all_thumbnails() -> int:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, original_filename, image_data FROM visual_images WHERE deleted_at IS NULL"
        ).fetchall()

    updated = 0
    for row in rows:
        cache_path = materialize_image(row["id"])
        thumb_bytes, thumb_mime, thumb_w, thumb_h = _thumbnail_bytes(cache_path)
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE visual_images
                SET thumbnail_data = ?, thumbnail_mime_type = ?, thumbnail_width = ?,
                    thumbnail_height = ?, thumbnail_generated_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (thumb_bytes, thumb_mime, thumb_w, thumb_h, now, row["id"]),
            )
            conn.commit()
        updated += 1
    return updated
