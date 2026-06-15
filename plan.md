# Plan: Add SAM2 Point Segmentation To Edit Page

## Goal

Use the new `core/point_to_segment.py` helper from the edit page so a user can create an inpaint mask from foreground/background clicks, then run the existing Photopea inpaint flow with that generated mask.

## Best Integration Direction

The best path is to treat SAM2 segmentation as a mask creation feature, not a separate generation mode. The edit page already supports mask-based inpaint:

- Photopea exports a current image as `i2i_input_*.png`.
- Photopea selection export can produce `selection_mask_*.png`.
- `handle_photopea_i2i(...)` receives `mask_path`.
- `generate_anima_inpaint_image(...)` already consumes `mask_image=mask_path`.
- Generated output is loaded back into Photopea as a new top layer.

SAM2 should produce a mask file that plugs into the same `mask_path` behavior.

## Recommended UX

Add a compact "Segment" control near the existing Photopea generation controls:

- A toggle or segmented control for point mode:
  - foreground point
  - background point
- Buttons:
  - clear points
  - preview mask
  - use mask for inpaint
- A small status line in the same control area:
  - waiting for points
  - segmenting
  - mask ready
  - segmentation failed

Avoid a separate page or modal-heavy workflow at first. The user should stay in `/edit`, click points, preview the mask, then run the same inpaint action.

## Point Collection Options

### Option A: Overlay Click Layer Outside Photopea

Export the current Photopea image to a temporary PNG, show it in a NiceGUI image preview with a click-capture overlay, and collect points there.

Pros:

- Easiest to implement and debug in NiceGUI.
- No need to inject more complex point-tracking JavaScript into Photopea.
- Click coordinates map directly to the exported image size.
- Segmentation preview can be shown before touching Photopea layers.

Cons:

- It is a separate preview surface, so the user is not clicking directly inside Photopea.
- Requires exporting the current Photopea image before segmentation.

This is the recommended first implementation.

### Option B: Capture Clicks Directly Inside Photopea

Inject JavaScript into Photopea to capture document click coordinates and send them back to NiceGUI.

Pros:

- Best long-term ergonomics.
- The user clicks exactly where they are editing.

Cons:

- Photopea coordinate handling, zoom/pan state, active tool state, and iframe event routing make this riskier.
- More likely to conflict with normal Photopea editing behavior.
- Harder to verify and debug.

This is a good second pass after the segmentation pipeline is proven.

### Option C: Use Current Photopea Selection As A Seed

Let the user make a rough Photopea selection, export that selection, derive sample points or a bounding region, then run SAM2.

Pros:

- Reuses familiar Photopea selection tools.
- Can improve segmentation for large subjects.

Cons:

- More complex than point clicks.
- SAM2 point prompting does not directly consume masks, so this would need conversion logic.

Keep this as a later refinement.

## Proposed Implementation Steps

1. Add a server-side helper in `pages/edit.py` or a small adjacent module:
   - export current Photopea image to `data/visual/temp/i2i_input_*.png`
   - store it as the active segmentation source
   - collect point records as `{x, y, label}`
   - call `segment_from_points(...)` via `run.io_bound(...)`
   - write outputs to `data/visual/temp/segment_<timestamp>/mask.png` and `overlay.png`

2. Extend `core/point_to_segment.py` for app reuse:
   - optionally add `mask_filename` and `overlay_filename` parameters
   - optionally return the number of masks or selected score metadata
   - keep model cache under `models/huggingface`

3. Add edit-page UI state:
   - `edit_segment_points`
   - `edit_segment_source_path`
   - `edit_segment_mask_path`
   - `edit_segment_overlay_path`
   - `edit_segment_status`

4. Build the first UI as a preview panel:
   - current exported image or overlay image
   - click handler records coordinates
   - foreground/background mode selector
   - clear, preview, and use buttons

5. When "preview mask" runs:
   - ensure a current image export exists
   - call SAM2 with collected points
   - show `overlay.png` in the preview panel
   - keep `mask.png` as `edit_segment_mask_path`

6. When "use mask for inpaint" runs:
   - export the current Photopea image again if needed
   - call the same logic as `photopea-i2i` with:
     - `path`: current image export
     - `mask_path`: SAM2 mask path
   - preserve the existing inpaint metadata path and generated-layer insertion behavior

## Important Technical Notes

- Coordinate mapping must be explicit. Store natural image width/height for the preview image and scale click coordinates back to natural pixels before calling SAM2.
- The SAM2 mask should be a binary white-on-black PNG, matching the selection mask behavior expected by `generate_anima_inpaint_image(...)`.
- Do not store segmentation points in durable user storage unless there is a clear reason. Treat them as edit-session state.
- Keep temporary segmentation outputs under `data/visual/temp` and include them in the existing temp cleanup pattern if needed.
- The model may take time to load. Show inline status near the segment controls instead of only a toast.
- If CUDA is unavailable, allow CPU fallback but make the status clear because segmentation will be slower.

## Verification Plan

- Syntax check:
  - `python -m py_compile pages\edit.py core\point_to_segment.py`
- Manual edit-page check:
  - open `/edit` with an image
  - export current image for segmentation
  - add one foreground point and one background point
  - preview mask
  - confirm `mask.png` and `overlay.png` are written under `data/visual/temp`
  - run inpaint with the SAM2 mask
  - confirm generated layer appears on top in Photopea
  - save final image and confirm metadata still records inpaint mode and current controls

## Future Enhancements

- Cache the loaded SAM2 predictor during the server process to avoid repeated model initialization.
- Add box prompts if the installed SAM2 API exposes them cleanly.
- Add mask refinement controls:
  - grow/shrink
  - blur edge
  - invert
  - keep largest component
- Add direct Photopea point picking once the preview-based path is stable.
