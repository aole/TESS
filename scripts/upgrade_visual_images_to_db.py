from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import initialize_database
from core.db.connection import get_connection
from core.db import visual_images_repo


VISUAL_DIR = ROOT / "data" / "visual" / "images"
HIDDEN_FILE = ROOT / "data" / "visual" / "hidden_images.json"
EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def load_hidden_names() -> set[str]:
    if not HIDDEN_FILE.exists():
        return set()
    try:
        data = json.loads(HIDDEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return set(data if isinstance(data, list) else [])


def load_imported_names() -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT original_filename
            FROM visual_images
            WHERE operation = 'legacy_import'
              AND original_filename IS NOT NULL
            """
        ).fetchall()
    return {row["original_filename"] for row in rows}


def main() -> None:
    initialize_database()
    hidden_names = load_hidden_names()
    imported_names = load_imported_names()
    if not VISUAL_DIR.exists():
        print("No data/visual/images directory found.")
        return

    imported = 0
    skipped = 0
    for path in sorted(VISUAL_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in EXTS:
            continue
        if path.name in imported_names:
            skipped += 1
            print(f"Skipped {path.name}")
            continue
        db_path = visual_images_repo.save_image_file(str(path).replace("\\", "/"), operation="legacy_import")
        if path.name in hidden_names:
            visual_images_repo.set_hidden(db_path, True)
        imported += 1
        print(f"Imported {path.name}")

    print(f"Imported {imported} image(s) into SQLite.")
    print(f"Skipped {skipped} already-imported image(s).")


if __name__ == "__main__":
    main()
