# Plan: Store Generated Images In The Database

## Goal

Save and retrieve generated images, thumbnails, and related metadata from SQLite. The database is the only durable image store; the filesystem may be used only for temporary/cache images needed by processing, previewing, or serving.

## Things To Do

1. Add image storage tables through the existing migration path:
   - `visual_images` for one row per generated, uploaded, edited, or processed image.
   - Store full image bytes and full thumbnail bytes in the same row.
   - Include created/updated timestamps, original filename, MIME type, width, height, file size, image bytes, thumbnail bytes, thumbnail MIME type, thumbnail width, thumbnail height, thumbnail generated timestamp, operation, optional comment, hidden flag, soft-delete fields, and JSON metadata.

2. Add queryable metadata columns plus raw metadata JSON:
   - Promote important fields into columns: prompt, negative prompt, seed, model, width, height, steps, CFG, denoising, Turbo LoRA, generation mode, operation, input image id/path, mask image id/path, and created timestamp.
   - Keep a JSON metadata column that can be written back into exported image files as PNG metadata.
   - Preserve existing PNG `parameters`, `tools`, and `source_metadata` data when present.

3. Add a database repository/service for visual image records:
   - create image record with bytes and metadata
   - attach or update thumbnail bytes on the image record
   - fetch image by id
   - fetch thumbnail columns by image id
   - list images for the visual gallery ordered by `created_at DESC`
   - update metadata, operation, and comment
   - hide/unhide image using a per-image flag
   - soft-delete image
   - permanently purge images after the configured retention window

4. Add a setting for permanent deletion retention:
   - Default soft-deleted images to a 30-day retention period.
   - Expose the retention period on the Settings page.
   - Add a cleanup routine that permanently deletes expired soft-deleted image rows.

5. Add a setting for maximum visual database size:
   - Default the maximum SQLite visual image storage size to 1 GB.
   - Put the value in the existing settings/config path so it can be changed later.
   - Check the configured limit before durable image writes.
   - Show a clear error when saving a new image would exceed the configured limit.

6. Update generation and save paths to write database records:
   - `services.visual_service.generate_image_task(...)`
   - visual upload handling
   - visual post-processing outputs such as upscale and background removal
   - edit-page saves from Photopea
   - edit-page i2i/inpaint generated outputs
   - any future visual operation that creates a durable image

7. Restrict filesystem image output to temporary/cache use:
   - Stop treating `data/visual/images` and `data/visual/thumbs` as durable storage.
   - Use temp files only when a library requires a file path or when serving/cache behavior needs one.
   - Clean up temp/cache files after use or through an existing temp cleanup path.
   - Keep durable image bytes, thumbnail bytes, and metadata in SQLite.

8. Update thumbnail creation and settings behavior:
   - Keep thumbnail generation centralized in `services.visual_service.create_thumbnail(...)` or a replacement helper with the same single responsibility.
   - Store thumbnail bytes, dimensions, format, MIME type, and generation timestamp on the image row.
   - When thumbnail settings change, show a confirmation popup to regenerate existing thumbnails.
   - If the user declines regeneration, revert the thumbnail settings change.

9. Update visual gallery retrieval:
   - Replace directory scanning in `data/visual/images` with database listing.
   - Sort by `created_at DESC`.
   - Preserve hidden-image filtering through the per-image hidden flag.
   - Preserve soft-deleted images outside normal gallery results.
   - Load thumbnails from SQLite instead of `data/visual/thumbs`.

10. Update image open/load/serve paths:
   - Resolve selected gallery items from database ids.
   - Add routes or helpers to serve image bytes and thumbnail bytes from SQLite.
   - Use temporary/cache files only when external tools, Photopea handoff, or browser serving requires a file path.
   - Keep export behavior able to write an image file with embedded metadata when the user saves or exports.

11. Add a standalone upgrade script:
    - Scan existing `data/visual/images`.
    - Read image bytes and PNG metadata with Pillow.
    - Create database records for existing images.
    - Read existing thumbnails from `data/visual/thumbs` into the matching image rows or regenerate missing thumbnails.
    - Preserve current hidden-image state from `data/visual/hidden_images.json`.
    - Respect the configured 1 GB visual database size limit.
    - Do not run this migration automatically on startup unless explicitly added later.

12. Add retrieval helpers for metadata consumers:
    - Visual page metadata panel.
    - Visual-to-edit handoff.
    - Visual-to-chat draft handoff.
    - Edit-page metadata inheritance for i2i settings.
    - PNG export metadata reconstruction from database fields plus raw JSON metadata.

13. Verify the migration:
    - Initialize a fresh database.
    - Run the standalone upgrade script against an existing image folder.
    - Generate a new image and confirm image bytes, thumbnail bytes, queryable metadata, and raw metadata are stored on one row.
    - Upload an image and confirm one row is created.
    - Save from `/edit` and confirm current edit metadata is stored.
    - Hide, unhide, soft-delete, restore if supported, and permanently purge expired image rows.
    - Change thumbnail settings, accept regeneration, and confirm existing image rows update their thumbnail columns.
    - Change thumbnail settings, decline regeneration, and confirm settings revert.
    - Reload the gallery and confirm it is ordered by `created_at DESC`.
    - Export an image and confirm PNG metadata is embedded from database metadata.
