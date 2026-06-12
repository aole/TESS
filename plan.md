# Plan: Send Visual Image(s) To Chat Draft

## Goal

In the visual page, add another image context-menu action that sends the selected image or selected images to a new chat as image attachments. The first image's generation metadata should provide the draft user prompt. The chat must open with the image attachment(s) and prompt already staged in the user input area, but it must not submit or start generation until the user edits and sends it.

## Things To Build

- Add a new visual context-menu item, likely named `Send to Chat`, beside the existing actions in `pages/components/visual_components.py`.
- Extend `VisualActionCallbacks` with a new callback for this action.
- Implement the visual-page callback in `pages/visual.py`.
- Reuse the existing `_context_action_targets(fpath)` behavior so the action works for:
  - the clicked image in full view,
  - the clicked image in grid view when there is no multi-selection,
  - all selected grid images when selection mode has multiple images selected.
- Normalize selected image paths into real local paths and skip or report missing files.
- Read generation metadata from the first selected image only.
- Extract the positive prompt from the first image metadata. The current metadata convention appears to store JSON under the PNG `parameters` key with fields like `prompt`, `negative_prompt`, `steps`, `width`, and `height`.
- Decide the handoff format from visual to chat. A practical shape is a temporary `app.storage.user` payload, for example:
  - `pending_chat_draft.prompt`
  - `pending_chat_draft.images`
  - `pending_chat_draft.source`
  - `pending_chat_draft.created_at`
- Navigate to `/chat?new=true` or another route/query that forces a new chat.
- Update `pages/chat.py` startup/input setup to consume the pending draft after the input area and local attachment lists exist.
- Populate `user_input.value` with the prompt from metadata.
- Populate `attached_images` with the selected images in the same structure the existing chat uploader uses:
  - `name`
  - `mime_type`
  - base64 `data`
- Refresh the attachment badge UI after preloading the images.
- Clear the pending draft payload after successful consumption so refreshes do not keep re-inserting the same prompt and attachments.
- Ensure the draft stays unsent. Do not append to `messages`, do not call `save_current_chat()`, and do not call `generate_response()` during preload.
- Do not notify the user if no metadata prompt is found, while still attaching the image(s). Just set the user input to 'No prompt found on the image.'.
- Add focused verification:
  - `python -m py_compile pages\visual.py pages\chat.py pages\components\visual_components.py`
- The first selected image is not hard and fast, what one image that is fastest to get.


## Ambiguities

- Menu label: should it be `Send to Chat`, `Attach to New Chat`, or something more explicit like `Draft in Chat`? send to chat
- Prompt source: should the draft use only `parameters.prompt`, or should it include `negative_prompt` too? only prompt
- Missing metadata fallback: if the first image has no prompt metadata, should the chat input be blank, use `Please analyze the attached image(s).`, or block the action with a warning? just say no metadata found on the image.
- Multiple selection order: should the "first image" mean sorted filename/path order, the image that was right-clicked, newest image, or selection order? does not matter, pick what is fastest.
- New chat behavior: should the feature always create a brand-new empty chat, or reuse the existing most recent empty chat as the current `/chat?new=true` flow does? new=true flow works.
- Existing unsaved chat draft: if the user already has a typed but unsent draft in chat, should this action replace it, append to it, or ask first? append.
- Prompt placement: should the staged prompt appear as plain user input only, or should it be wrapped with a short instruction for the chat model? plain user input only.
- Attachment persistence before send: should staged images be held as base64 in browser/session storage, or should only trusted local file paths be passed and encoded inside `chat.py`? paths shouldbe passed and should be encoded in chat.py
- Selection scope: should the action be available in full view for only the current image, or should it honor grid selections even when a full-view image is open? full view takes presidence.
- Success feedback: should visual show a notification before navigation, or should chat show one after the draft is staged? show chat
