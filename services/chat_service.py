import json
import os
import uuid
import asyncio
from utils import encription
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict



# Define storage directory
CHATS_DIR = os.path.join(os.getcwd(), 'data', 'chats')

@dataclass
class ChatSession:
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[Dict]
    is_encrypted: bool = False
    salt: Optional[str] = None

class ChatService:
    def __init__(self):
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(CHATS_DIR, exist_ok=True)

    def _get_file_path(self, chat_id: str) -> str:
        return os.path.join(CHATS_DIR, f"{chat_id}.json")

    def create_chat(self, title: str = "New Chat") -> ChatSession:
        chat_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        chat = ChatSession(
            id=chat_id,
            title=title,
            created_at=now,
            updated_at=now,
            messages=[]
        )
        self.save_chat(chat)
        return chat

    def save_chat(self, chat: ChatSession, update_timestamp: bool = True):
        if update_timestamp:
            chat.updated_at = datetime.now().isoformat()
        try:
            with open(self._get_file_path(chat.id), 'w', encoding='utf-8') as f:
                json.dump(asdict(chat), f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving chat {chat.id}: {e}")

    def load_chat(self, chat_id: str) -> Optional[ChatSession]:
        path = self._get_file_path(chat_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return ChatSession(**data)
        except Exception as e:
            print(f"Error loading chat {chat_id}: {e}")
            return None

    def list_chats(self) -> List[Dict]:
        """Returns a list of chat summaries (id, title, updated_at) sorted by updated_at desc."""
        chats = []
        if not os.path.exists(CHATS_DIR):
            return []
        
        for filename in os.listdir(CHATS_DIR):
            if filename.endswith('.json'):
                path = os.path.join(CHATS_DIR, filename)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        # Just read enough to get metadata if possible, but JSON needs full load usually.
                        # For now, load all. Optimization later if needed.
                        data = json.load(f)
                        chats.append({
                            'id': data.get('id'),
                            'title': data.get('title', 'Untitled'),
                            'updated_at': data.get('updated_at', ''),
                            'preview': self._get_preview(data.get('messages', [])),
                            'is_encrypted': data.get('is_encrypted', False)
                        })
                except Exception as e:
                    print(f"Error listing chat {filename}: {e}")
        
        # Sort by updated_at descending
        chats.sort(key=lambda x: x['updated_at'], reverse=True)
        return chats

    def delete_chat(self, chat_id: str):
        path = self._get_file_path(chat_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"Error deleting chat {chat_id}: {e}")

    def update_title(self, chat_id: str, new_title: str):
        chat = self.load_chat(chat_id)
        if chat:
            chat.title = new_title
            self.save_chat(chat)

    def _get_preview(self, messages: List[Dict]) -> str:
        if not messages:
            return "Empty chat"
        last_msg = messages[-1]
        content = last_msg.get('content', '')
        if len(content) > 60:
            return content[:57] + "..."
        return content

    def verify_password(self, chat_id: str, password: str) -> bool:
        chat = self.load_chat(chat_id)
        if not chat or not chat.is_encrypted or not chat.salt:
            return True
        return encription.verify_encrypted_messages(chat.messages, chat.salt, password)

    def decrypt_messages(self, messages: List[Dict], password: str, salt: str) -> List[Dict]:
        return encription.decrypt_messages(messages, password, salt)

    def encrypt_messages(self, messages: List[Dict], password: str, salt: str) -> List[Dict]:
        return encription.encrypt_messages(messages, password, salt)

chat_service = ChatService()
