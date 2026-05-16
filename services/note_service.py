import json
import os
import logging
import threading
from datetime import datetime
import uuid

DATA_DIR = 'data'
NOTES_FILE = os.path.join(DATA_DIR, 'notes.json')

class NoteService:
    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, 'w') as f:
                json.dump([], f)

    def _is_drive_available(self) -> bool:
        """Returns True if a Google account is connected and credentials are valid."""
        try:
            from services.google_service import google_service
            return google_service.is_account_valid()
        except Exception:
            return False

    def _get_local_notes(self):
        try:
            with open(NOTES_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _get_drive_notes(self):
        try:
            from services.google_service import google_service
            content = google_service.read_drive_file('notes.json')
            if content:
                return json.loads(content)
        except Exception as e:
            logging.warning(f"Could not read notes from Drive: {e}")
        return []

    def _save_local_notes(self, notes):
        with open(NOTES_FILE, 'w') as f:
            json.dump(notes, f, indent=2)

    def _save_drive_notes(self, notes):
        try:
            from services.google_service import google_service
            google_service.save_drive_file('notes.json', json.dumps(notes, indent=2))
        except Exception as e:
            logging.warning(f"Could not save notes to Drive: {e}")

    def get_notes(self):
        """Return local notes for immediate UI feedback."""
        return self._get_local_notes()

    def add_note(self, content, category="General"):
        notes = self._get_local_notes()
        new_note = {
            'id': str(uuid.uuid4()),
            'content': content,
            'category': category,
            'timestamp': datetime.now().isoformat()
        }
        notes.insert(0, new_note)
        self._save_notes(notes)
        return new_note

    def delete_note(self, note_id):
        notes = self._get_local_notes()
        notes = [n for n in notes if n['id'] != note_id]
        self._save_notes(notes)

    def _save_notes(self, notes):
        """Save locally, then push to Drive in background if an account is connected."""
        self._save_local_notes(notes)
        if self._is_drive_available():
            threading.Thread(target=self._save_drive_notes, args=(notes,), daemon=True).start()

    def sync_notes(self):
        """
        Pulls notes from Google Drive, merges with local notes (union by ID,
        newest timestamp wins on conflict), then saves the result to both
        local disk and Drive.

        Returns the total number of notes after merge, or -1 if Drive is unavailable.
        """
        if not self._is_drive_available():
            logging.info("sync_notes: Drive not available, skipping.")
            return -1

        local_notes = self._get_local_notes()
        drive_notes = self._get_drive_notes()

        merged = {}
        for n in local_notes + drive_notes:
            nid = n.get('id')
            if not nid:
                continue
            if nid not in merged:
                merged[nid] = n
            else:
                # Conflict: keep the version with the later timestamp
                existing = merged[nid]
                try:
                    ts_exist = datetime.fromisoformat(existing.get('timestamp', ''))
                    ts_new = datetime.fromisoformat(n.get('timestamp', ''))
                    if ts_new > ts_exist:
                        merged[nid] = n
                except Exception:
                    pass  # Keep existing on parse failure

        final_notes = sorted(merged.values(), key=lambda x: x.get('timestamp', ''), reverse=True)

        self._save_local_notes(final_notes)
        self._save_drive_notes(final_notes)

        # Record sync time
        from utils.config import config_manager
        config_manager.set_last_notes_sync(datetime.now().isoformat())

        return len(final_notes)

note_service = NoteService()
