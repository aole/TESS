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

    def _get_local_notes(self):
        try:
            with open(NOTES_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _get_drive_notes(self):
        from services.google_service import google_service
        content = google_service.read_drive_file('notes.json')
        if content:
            try:
                return json.loads(content)
            except:
                return []
        return []

    def _save_local_notes(self, notes):
        with open(NOTES_FILE, 'w') as f:
            json.dump(notes, f, indent=2)

    def _save_drive_notes(self, notes):
        from services.google_service import google_service
        google_service.save_drive_file('notes.json', json.dumps(notes, indent=2))

    def get_notes(self):
        # Always return local notes for immediate UI feedback.
        # Syncing happens in background or via Settings explicit sync.
        return self._get_local_notes()

    def add_note(self, content, category="General"):
        notes = self._get_local_notes()
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
        notes = self._get_local_notes()
        notes = [n for n in notes if n['id'] != note_id]
        self._save_notes(notes)

    def _save_notes(self, notes):
        # 1. Save local immediately
        self._save_local_notes(notes)
        
        # 2. Check config and sync to Drive in background
        from utils.config import config_manager
        storage = config_manager.get_note_storage()
        
        if storage == 'google_drive':
            # Fire and forget background sync
            import threading
            threading.Thread(target=self._save_drive_notes, args=(notes,)).start()

    def sync_notes(self):
        """
        Merges notes from both local and Google Drive storage, 
        and saves the union to both locations.
        """
        local_notes = self._get_local_notes()
        drive_notes = self._get_drive_notes()
        
        # Merge logic: Use dictionary keyed by ID
        # Prefer the version with the later timestamp if conflict (though rare if IDs are unique uuids)
        # Actually, if we just want union of distinct notes:
        merged = {}
        
        for n in local_notes + drive_notes:
            nid = n.get('id')
            if not nid: continue
            
            if nid not in merged:
                merged[nid] = n
            else:
                # Conflict resolution: compare timestamps
                existing = merged[nid]
                try:
                    ts_exist = datetime.fromisoformat(existing.get('timestamp', ''))
                    ts_new = datetime.fromisoformat(n.get('timestamp', ''))
                    if ts_new > ts_exist:
                        merged[nid] = n
                except:
                    # If timestamp parsing fails, keep existing or new? Keep existing for stability
                    pass
        
        # Convert back to list and sort by timestamp descending
        final_notes = list(merged.values())
        final_notes.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Save to both
        self._save_local_notes(final_notes)
        self._save_drive_notes(final_notes)
        
        return len(final_notes)

note_service = NoteService()
