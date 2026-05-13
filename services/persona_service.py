import json
import os
import uuid
from typing import Optional

DATA_DIR = 'data'
PERSONAS_FILE = os.path.join(DATA_DIR, 'personas.json')

# Sentinel used for "no persona / no system prompt"
NO_PERSONA_ID = '__none__'
NO_PERSONA = {
    'id': NO_PERSONA_ID,
    'name': 'None (no system prompt)',
    'system_prompt': '',
}



class PersonaService:
    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(PERSONAS_FILE):
            initial = {
                'personas': [],
                'default_persona_id': NO_PERSONA_ID,
            }
            with open(PERSONAS_FILE, 'w') as f:
                json.dump(initial, f, indent=2)

    def _load(self) -> dict:
        """Load the full data dict (personas list + default_persona_id)."""
        try:
            with open(PERSONAS_FILE, 'r') as f:
                data = json.load(f)
            # Migrate old list-only format
            if isinstance(data, list):
                data = {
                    'personas': data,
                    'default_persona_id': NO_PERSONA_ID,
                }
                self._save_data(data)
            # Fix stale __helpful_assistant__ sentinel left from a previous version
            if data.get('default_persona_id') == '__helpful_assistant__':
                data['default_persona_id'] = NO_PERSONA_ID
                self._save_data(data)
            return data
        except Exception:
            return {'personas': [], 'default_persona_id': NO_PERSONA_ID}

    def get_personas(self) -> list:
        """Return all user-defined personas (does NOT include the built-in None entry)."""
        return self._load().get('personas', [])

    def get_all_persona_options(self) -> list:
        """Return all options including the built-in 'None' sentinel at the top."""
        return [NO_PERSONA] + self.get_personas()

    def get_default_persona_id(self) -> str:
        return self._load().get('default_persona_id', NO_PERSONA_ID)

    def set_default_persona_id(self, persona_id: str):
        data = self._load()
        data['default_persona_id'] = persona_id
        self._save_data(data)

    def get_default_persona(self) -> dict:
        pid = self.get_default_persona_id()
        if pid == NO_PERSONA_ID:
            return NO_PERSONA
        for p in self.get_personas():
            if p['id'] == pid:
                return p
        return NO_PERSONA

    def add_persona(self, name: str, system_prompt: str) -> dict:
        data = self._load()
        new_persona = {
            'id': str(uuid.uuid4()),
            'name': name.strip(),
            'system_prompt': system_prompt.strip(),
        }
        data['personas'].append(new_persona)
        self._save_data(data)
        return new_persona

    def update_persona(self, persona_id: str, name: str, system_prompt: str) -> bool:
        data = self._load()
        for p in data['personas']:
            if p['id'] == persona_id:
                p['name'] = name.strip()
                p['system_prompt'] = system_prompt.strip()
                self._save_data(data)
                return True
        return False

    def delete_persona(self, persona_id: str) -> bool:
        data = self._load()
        old_len = len(data['personas'])
        data['personas'] = [p for p in data['personas'] if p['id'] != persona_id]
        if len(data['personas']) == old_len:
            return False
        # Reset default if deleted persona was the default
        if data.get('default_persona_id') == persona_id:
            data['default_persona_id'] = NO_PERSONA_ID
        self._save_data(data)
        return True

    def get_persona(self, persona_id: str) -> Optional[dict]:
        if persona_id == NO_PERSONA_ID:
            return NO_PERSONA
        for p in self.get_personas():
            if p['id'] == persona_id:
                return p
        return None

    def _save_data(self, data: dict):
        with open(PERSONAS_FILE, 'w') as f:
            json.dump(data, f, indent=2)


persona_service = PersonaService()
