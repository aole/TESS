import json
import os
import uuid
from typing import Optional

DATA_DIR = 'data'
PERSONAS_FILE = os.path.join(DATA_DIR, 'personas.json')


class PersonaService:
    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(PERSONAS_FILE):
            with open(PERSONAS_FILE, 'w') as f:
                json.dump([], f)

    def get_personas(self) -> list:
        try:
            with open(PERSONAS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def add_persona(self, name: str, system_prompt: str) -> dict:
        personas = self.get_personas()
        new_persona = {
            'id': str(uuid.uuid4()),
            'name': name.strip(),
            'system_prompt': system_prompt.strip(),
        }
        personas.append(new_persona)
        self._save(personas)
        return new_persona

    def update_persona(self, persona_id: str, name: str, system_prompt: str) -> bool:
        personas = self.get_personas()
        for p in personas:
            if p['id'] == persona_id:
                p['name'] = name.strip()
                p['system_prompt'] = system_prompt.strip()
                self._save(personas)
                return True
        return False

    def delete_persona(self, persona_id: str) -> bool:
        personas = self.get_personas()
        new_list = [p for p in personas if p['id'] != persona_id]
        if len(new_list) == len(personas):
            return False
        self._save(new_list)
        return True

    def get_persona(self, persona_id: str) -> Optional[dict]:
        for p in self.get_personas():
            if p['id'] == persona_id:
                return p
        return None

    def _save(self, personas: list):
        with open(PERSONAS_FILE, 'w') as f:
            json.dump(personas, f, indent=2)


persona_service = PersonaService()
