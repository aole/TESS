from nicegui import ui, app
import secrets
import asyncio
from typing import List, Callable, Dict, Any

from utils.llm_client import client
from services.tool_service import tool_service
from services.rating_service import rating_service
from services.chat_service import chat_service

class SettingsDialog:
    def __init__(self, 
                 model_options: List[str],
                 on_clear_chat: Callable,
                 on_chat_updated: Callable,
                 get_current_chat_id: Callable[[], str],
                 get_messages: Callable[[], List[Dict]],
                 model_select_component: ui.select = None # Optional: if we want to sync with an external model select
                 ):
        self.model_options = model_options
        self.on_clear_chat = on_clear_chat
        self.on_chat_updated = on_chat_updated
        self.get_current_chat_id = get_current_chat_id
        self.get_messages = get_messages
        self.model_select_component = model_select_component
        
        self.dialog = None
        self.tool_checks = {}
        
        # Security Buttons (references to be set during build)
        self.settings_encrypt_btn = None
        self.settings_remove_enc_btn = None
        self.settings_unlock_btn = None
        self.settings_lock_btn = None
        
        self._build_dialog()

    def _build_dialog(self):
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-lg p-6 bg-[#18181b] border border-white/10'):
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('Settings').classes('text-xl font-bold text-gray-200')
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense color=grey')

            with ui.column().classes('w-full gap-4'):
                # Security (Encryption)
                with ui.expansion('Security', icon='security').classes('w-full bg-white/5 rounded-lg').props('dense'):
                    with ui.column().classes('w-full p-2 gap-2'):
                        ui.label('Protect your chat history with a password.').classes('text-xs text-gray-400')
                        self.settings_encrypt_btn = ui.button('Encrypt Chat', icon='lock', on_click=self.prompt_encryption).props('outline color=primary').classes('w-full')
                        self.settings_remove_enc_btn = ui.button('Remove Encryption', icon='lock_open', on_click=self.prompt_remove_encryption).props('outline color=negative').classes('w-full hidden')
                        self.settings_unlock_btn = ui.button('Unlock Chat', icon='key', on_click=self.prompt_unlock).props('outline color=warning').classes('w-full hidden')
                        self.settings_lock_btn = ui.button('Lock Chat', icon='lock', on_click=self.do_lock).props('outline color=warning').classes('w-full hidden')

                # Action Buttons
                ui.button('Clear Chat History', on_click=self.on_clear_chat).props('flat color=negative').classes('w-full mt-4')

    def open(self):
        self.sync_ui_from_storage()
        self.dialog.open()

    def close(self):
        self.dialog.close()

    def sync_ui_from_storage(self):
        self.update_encryption_ui()

    # --- Encryption Logic ---

    def update_encryption_ui(self):
        current_chat_id = self.get_current_chat_id()
        if not current_chat_id:
            self.settings_encrypt_btn.classes(add='hidden')
            self.settings_unlock_btn.classes(add='hidden')
            self.settings_lock_btn.classes(add='hidden')
            self.settings_remove_enc_btn.classes(add='hidden')
            return

        chat = chat_service.load_chat(current_chat_id)
        if not chat: return
        
        if chat.is_encrypted:
            self.settings_encrypt_btn.classes(add='hidden')
            pw = app.storage.user.get('unlocked_chats', {}).get(current_chat_id)
            is_unlocked = pw and chat_service.verify_password(current_chat_id, pw)
            
            if is_unlocked:
                self.settings_unlock_btn.classes(add='hidden')
                self.settings_lock_btn.classes(remove='hidden')
                self.settings_remove_enc_btn.classes(remove='hidden')
            else:
                self.settings_unlock_btn.classes(remove='hidden')
                self.settings_lock_btn.classes(add='hidden')
                self.settings_remove_enc_btn.classes(add='hidden')
        else:
            self.settings_encrypt_btn.classes(remove='hidden')
            self.settings_unlock_btn.classes(add='hidden')
            self.settings_lock_btn.classes(add='hidden')
            self.settings_remove_enc_btn.classes(add='hidden')

    async def prompt_encryption(self):
        with ui.dialog() as d, ui.card().classes('bg-[#18181b] border border-white/10'):
            ui.label('Encrypt Chat').classes('text-lg font-bold text-gray-200')
            pw1 = ui.input('Password', password=True, password_toggle_button=True).classes('w-full')
            pw2 = ui.input('Confirm Password', password=True, password_toggle_button=True).classes('w-full')
            
            async def do_encrypt():
                current_chat_id = self.get_current_chat_id()
                messages = self.get_messages()
                if not pw1.value or pw1.value != pw2.value:
                    ui.notify('Passwords do not match or empty', type='negative')
                    return
                chat = chat_service.load_chat(current_chat_id)
                if chat:
                    chat.is_encrypted = True
                    chat.salt = secrets.token_hex(16)
                    garbage_messages = chat_service.encrypt_messages(messages, pw1.value, chat.salt)
                    chat.messages = garbage_messages
                    chat_service.save_chat(chat, update_timestamp=False)
                    
                    app.storage.user.get('unlocked_chats', {}).pop(current_chat_id, None)
                    
                    messages.clear()
                    messages.extend(garbage_messages)
                    app.storage.user['messages'] = messages
                    self.on_chat_updated()
                    
                    ui.notify('Chat encrypted', type='positive')
                    self.update_encryption_ui()
                d.close()
            ui.button('Encrypt', on_click=do_encrypt).props('color=primary').classes('w-full mt-2')
        await d

    async def prompt_unlock(self):
        current_chat_id = self.get_current_chat_id()
        with ui.dialog() as d, ui.card().classes('bg-[#18181b] border border-white/10'):
            ui.label('Unlock Chat').classes('text-lg font-bold text-gray-200')
            pw = ui.input('Password', password=True, password_toggle_button=True).classes('w-full').on('keydown.enter', lambda: do_unlock())
            
            async def do_unlock():
                if chat_service.verify_password(current_chat_id, pw.value):
                    if 'unlocked_chats' not in app.storage.user:
                        app.storage.user['unlocked_chats'] = {}
                    app.storage.user['unlocked_chats'][current_chat_id] = pw.value
                    self.on_chat_updated(chat_id=current_chat_id) # Signal to reload
                    ui.notify('Chat unlocked', type='positive')
                    d.close()
                    self.update_encryption_ui()
                else:
                    ui.notify('Incorrect password', type='negative')
            ui.button('Unlock', on_click=do_unlock).props('color=warning').classes('w-full mt-2')
        await d

    async def prompt_remove_encryption(self):
        current_chat_id = self.get_current_chat_id()
        messages = self.get_messages()
        chat = chat_service.load_chat(current_chat_id)
        if chat:
            chat.is_encrypted = False
            chat.salt = None
            app.storage.user.get('unlocked_chats', {}).pop(current_chat_id, None)
            chat.messages = messages
            chat_service.save_chat(chat, update_timestamp=False)
            ui.notify('Encryption removed', type='info')
            self.update_encryption_ui()

    def do_lock(self):
        current_chat_id = self.get_current_chat_id()
        app.storage.user.get('unlocked_chats', {}).pop(current_chat_id, None)
        self.on_chat_updated(chat_id=current_chat_id) # Signal to reload (will load as encrypted)
        ui.notify('Chat locked', type='info')
        self.update_encryption_ui()
