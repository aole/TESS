# Plan: Make Visual Prompts Die With Server Session

## Goal

On the visual page, the positive prompt and negative prompt must not survive a server restart. After restarting the server, the prompt fields should return to the intended fresh defaults instead of restoring whatever the user typed in a previous run.

## Things To Do

- Confirm the current persistence path in `pages/visual.py`:
  - `initialize_user_defaults()` seeds `visual_positive_prompt` and `visual_negative_prompt`.
  - The UI textareas bind directly to `app.storage.user` keys with `.bind_value(...)`.
  - `app.storage.user` can survive server restarts, which is why stale prompt text comes back.
- Decide the storage boundary for only these two fields:
  - Keep other visual settings persistent unless explicitly changed by this task.
  - Stop treating `visual_positive_prompt` and `visual_negative_prompt` as durable user preferences.
- Introduce server-lifetime defaults for prompt fields:
  - On every server process start, the first visit should use the built-in positive prompt and built-in negative prompt.
  - User edits during the current running server session should remain available while navigating within the app.
  - After server restart, previous prompt edits should be ignored or cleared.
- Choose an implementation pattern that matches the current NiceGUI code:
  - Option A: use a module-level server-session dictionary keyed by user/session id for only the prompt fields.
  - Option B: keep binding to `app.storage.user`, but stamp prompt values with a server-start token and reset them when the token changes.
  - Option C: stop storing these fields in persistent storage and keep them in page-local state, if page reload persistence is not needed.
- Update `initialize_user_defaults()` so it no longer preserves old prompt values across server restarts.
- Update the positive and negative prompt textareas so their values still work with existing generation paths:
  - `generate_images(...)`
  - image-to-image generation from the visual page
  - context-menu "Generate Prompt with AI"
  - any code that reads `app.storage.user['visual_positive_prompt']` or `['visual_negative_prompt']`
- Ensure AI prompt generation still updates both the visible textarea and the current server-session prompt state.
- Ensure failed AI prompt generation restores only the current session prompt value, not an older persisted value.
- Audit for any other prompt writes in `pages/visual.py` that would re-persist stale values after the reset.
- Add a narrow cleanup/migration step if needed:
  - Remove stale `visual_positive_prompt` and `visual_negative_prompt` from `app.storage.user`, or overwrite them on server-session mismatch.
  - Do not remove unrelated visual settings like width, height, steps, CFG, Turbo LoRA, upscale, hidden-image state, or remove-background settings.
- Verify behavior manually:
  - Start the server and open the visual page.
  - Change positive and negative prompts.
  - Navigate away and back; confirm the prompts behave according to the chosen session rule.
  - Restart the server.
  - Reopen the visual page; confirm the old typed prompts are gone.
- Run focused syntax verification:
  - `python -m py_compile pages\visual.py pages\edit.py core\session_state.py`
- Bump `version.txt` after implementation.

## Decisions

- "Session" means server process lifetime.
- Visual prompt edits should survive navigation away from `/visual` and back while the server is still running.
- Visual prompt edits should survive browser refresh while the server is still running.
- After a server restart, the visual positive prompt and negative prompt should reset to their current defaults.
- "Generate Prompt with AI" results should be session-scoped the same way typed prompt edits are.
- Old persisted prompt values should be deleted from user storage, not merely ignored.
- The same server-session reset should apply to edit-page image-to-image prompts:
  - `edit_i2i_prompt`
  - `edit_i2i_neg_prompt`
- The old edit-page session PSD should also be deleted after server restart.
- Generated image metadata should still record the prompt and negative prompt used for the image.
