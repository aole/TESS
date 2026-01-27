from typing import Dict, List, Optional
import uuid
import datetime

class ArenaService:
    def __init__(self):
        # battle_id -> state dict
        self.battles: Dict[str, Dict] = {}

    def start_battle(self, model1: str, model2: str, system_prompt: str) -> str:
        battle_id = str(uuid.uuid4())
        self.battles[battle_id] = {
            'id': battle_id,
            'model1': model1,
            'model2': model2,
            'system_prompt': system_prompt,
            'messages1': [], # List of message dicts
            'messages2': [],
            'created_at': datetime.datetime.now().isoformat(),
            'stream_id_1': f"{battle_id}_1",
            'stream_id_2': f"{battle_id}_2"
        }
        return battle_id

    def get_battle(self, battle_id: str) -> Optional[Dict]:
        return self.battles.get(battle_id)
    
    # We might not need explicit save methods if we modify the message lists in place via reference, 
    # but it's good to have a way to update if needed.
    # Since StreamService updates the list object in place, the reference held here will be updated.

arena_service = ArenaService()
