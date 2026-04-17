import json
import uuid
import base64
from typing import List, Dict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def verify_encrypted_messages(messages: List[Dict], salt_hex: str, password: str) -> bool:
    try:
        salt_bytes = bytes.fromhex(salt_hex)
        key = _derive_key(password, salt_bytes)
        f = Fernet(key)
        encrypted_data = messages[0]['content'].encode('utf-8')
        f.decrypt(encrypted_data)
        return True
    except:
        return False

def decrypt_messages(messages: List[Dict], password: str, salt_hex: str) -> List[Dict]:
    if not messages or not salt_hex: return messages
    salt_bytes = bytes.fromhex(salt_hex)
    key = _derive_key(password, salt_bytes)
    f = Fernet(key)
    encrypted_data = messages[0]['content']
    decrypted_bytes = f.decrypt(encrypted_data.encode('utf-8'))
    return json.loads(decrypted_bytes.decode('utf-8'))

def encrypt_messages(messages: List[Dict], password: str, salt_hex: str) -> List[Dict]:
    salt_bytes = bytes.fromhex(salt_hex)
    key = _derive_key(password, salt_bytes)
    f = Fernet(key)
    data = json.dumps(messages).encode('utf-8')
    encrypted_data = f.encrypt(data).decode('utf-8')
    return [{'role': 'assistant', 'content': encrypted_data, 'id': str(uuid.uuid4())}]
