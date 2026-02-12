import json
import os
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

    CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')

    def get_notes(self):
        from utils.config import config_manager
        storage = config_manager.get_note_storage()
        
        if storage == 'google_drive':
            from services.google_service import google_service
            content = google_service.read_drive_file('notes.json')
            if content:
                try:
                    return json.loads(content)
                except:
                    return []
            return []
        
        # Local fallback
        try:
            with open(NOTES_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def add_note(self, content, category="General"):
        # Note: This is now potentially slow if using Drive
        notes = self.get_notes()
        new_note = {
            'id': str(uuid.uuid4()),
            'content': content,
            'category': category,
            'timestamp': datetime.now().isoformat()
        }
        # Insert at the beginning
        notes.insert(0, new_note)
        self._save_notes(notes)
        return new_note

    def delete_note(self, note_id):
        notes = self.get_notes()
        notes = [n for n in notes if n['id'] != note_id]
        self._save_notes(notes)

    def _save_notes(self, notes):
        from utils.config import config_manager
        storage = config_manager.get_note_storage()
        
        if storage == 'google_drive':
            from services.google_service import google_service
            google_service.save_drive_file('notes.json', json.dumps(notes, indent=2))
            # Also save local backup? Optional. For now exclusive.
            return

        with open(NOTES_FILE, 'w') as f:
            json.dump(notes, f, indent=2)

note_service = NoteService()
