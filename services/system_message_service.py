from datetime import datetime
import json
import os
import uuid
from typing import Dict, Callable, Optional


DATA_DIR = 'data'
SYSTEM_VARIABLES_FILE = os.path.join(DATA_DIR, 'system_variables.json')


class SystemMessageService:
    """Service to compile and provide the final system message sent to the model."""

    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(SYSTEM_VARIABLES_FILE):
            self._save_custom_variables([])

    def _load_custom_variables(self) -> list:
        self._ensure_file()
        try:
            with open(SYSTEM_VARIABLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_custom_variables(self, variables: list):
        with open(SYSTEM_VARIABLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(variables, f, indent=2)

    def _normalize_variable_name(self, name: str) -> str:
        import re

        normalized = re.sub(r'[^A-Za-z0-9_]+', '_', name.strip().upper())
        return normalized.strip('_')

    def get_builtin_variables(self) -> list:
        now = datetime.now()
        return [
            {
                'name': 'CURRENT_DATE_TIME',
                'value': now.strftime('%b-%d-%Y %I:%M:%S %p'),
            },
            {
                'name': 'CURRENT_DATE',
                'value': now.strftime('%b-%d-%Y'),
            },
            {
                'name': 'CURRENT_TIME',
                'value': now.strftime('%I:%M:%S %p'),
            },
            {
                'name': 'DAY_OF_WEEK',
                'value': now.strftime('%A'),
            },
        ]

    def get_custom_variables(self) -> list:
        return self._load_custom_variables()

    def get_reserved_variable_names(self) -> set[str]:
        return {var['name'] for var in self.get_builtin_variables()}

    def add_custom_variable(self, name: str, value: str) -> tuple[bool, str]:
        normalized = self._normalize_variable_name(name)
        if not normalized:
            return False, 'Name is required'
        if normalized in self.get_reserved_variable_names():
            return False, 'That name is reserved'

        variables = self._load_custom_variables()
        if any(var['name'] == normalized for var in variables):
            return False, 'A variable with that name already exists'

        variables.append({
            'id': str(uuid.uuid4()),
            'name': normalized,
            'value': value,
        })
        self._save_custom_variables(variables)
        return True, normalized

    def update_custom_variable(self, variable_id: str, name: str, value: str) -> tuple[bool, str]:
        normalized = self._normalize_variable_name(name)
        if not normalized:
            return False, 'Name is required'
        if normalized in self.get_reserved_variable_names():
            return False, 'That name is reserved'

        variables = self._load_custom_variables()
        if any(var['id'] != variable_id and var['name'] == normalized for var in variables):
            return False, 'A variable with that name already exists'

        for var in variables:
            if var['id'] == variable_id:
                var['name'] = normalized
                var['value'] = value
                self._save_custom_variables(variables)
                return True, normalized
        return False, 'Variable not found'

    def delete_custom_variable(self, variable_id: str) -> bool:
        variables = self._load_custom_variables()
        filtered = [var for var in variables if var['id'] != variable_id]
        if len(filtered) == len(variables):
            return False
        self._save_custom_variables(filtered)
        return True

    def _read_text_file(self, path: str) -> str:
        raw_path = path.strip().strip('"\'')
        if not raw_path:
            return ''

        data_root = os.path.abspath(DATA_DIR)
        normalized_raw = raw_path.replace('\\', os.sep).replace('/', os.sep)
        if os.path.isabs(normalized_raw):
            resolved_path = os.path.abspath(normalized_raw)
        else:
            parts = normalized_raw.split(os.sep)
            if parts and parts[0].lower() == DATA_DIR.lower():
                normalized_raw = os.sep.join(parts[1:])
            resolved_path = os.path.abspath(os.path.join(data_root, normalized_raw))

        try:
            common_path = os.path.commonpath([data_root, resolved_path])
        except ValueError:
            common_path = ''
        if common_path != data_root:
            return f'[Unable to read file: {raw_path} (path must be inside data)]'

        try:
            with open(resolved_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(resolved_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except OSError as e:
            return f'[Unable to read file: {raw_path} ({e.strerror})]'

    def resolve_variable_value(self, value: str) -> str:
        """
        Resolve custom variable values.

        Syntax:
            @file(path/to/file.txt)

        Paths are resolved from the data directory. Absolute paths are allowed
        only when they point inside data.
        """
        if not value:
            return ''

        import re

        match = re.fullmatch(r'\s*@file\((.+)\)\s*', value, re.DOTALL)
        if not match:
            return value

        return self._read_text_file(match.group(1))
    
    def replace_system_variables(self, text: str) -> str:
        """
        Replaces variables like {{CURRENT_DATE_TIME}}, {{CURRENT_DATE}},
        {{CURRENT_TIME}}, {{DAY_OF_WEEK}} in the text with their current values.
        """
        if not text:
            return ""
            
        import re
        
        replacements = {var['name']: var['value'] for var in self.get_builtin_variables()}
        replacements.update({
            var['name']: self.resolve_variable_value(var.get('value', ''))
            for var in self.get_custom_variables()
        })
        
        def repl(match):
            var_name = match.group(1).strip().upper()
            return replacements.get(var_name, match.group(0))
            
        # Case-insensitive replacement, matching {{VARIABLE_NAME}} with optional spaces
        return re.sub(r'\{\{\s*([A-Za-z0-9_]+)\s*\}\}', repl, text)
    
    def compile_message(
        self,
        base_prompt: str = "",
        memory_enabled: bool = False,
        has_attachments: bool = False,
        tool_funcs_map: Optional[Dict[str, Callable]] = None,
        has_tools: bool = False,
    ) -> str:
        """
        Compiles the final system message based on various features and context.
        
        Args:
            base_prompt: The base system prompt (from persona, setting, or user input).
            memory_enabled: Whether to append long-term memory instructions.
            has_attachments: Whether to append document attachment instructions.
            tool_funcs_map: Optional dictionary of active tool functions.
            has_tools: Optional flag to indicate tools are present/active even if map is not passed.
            
        Returns:
            The fully compiled system message string.
        """
        # 1. Base system prompt
        sys_content = base_prompt or ""
        sys_content = self.replace_system_variables(sys_content)
        
        # 3. Memory Instructions
        if memory_enabled:
            memory_instructions = """
# ROLE
You have "Long-Term Memory." Your goal is to provide a highly personalized experience by remembering user details, family relations, preferences, and history across conversations.

# OPERATIONAL RULES
- TOOL AVAILABILITY: You may have access to tools for managing user memory (update_user_info, get_user_info, delete_user_info). Always check if these tools are available/selected before attempting to call them. 
- AUTOMATIC STORAGE: If the `update_user_info` tool is available, use it silently and immediately whenever the user mentions a personal detail (e.g., "I'm 30," "My wife's name is Chloe," "I hate cilantro"). Do not ask for permission to save information.
- PROACTIVE RETRIEVAL: If the `get_user_info` tool is available, you MUST use it at the very start of a session or if you realize you don't know who you are talking to. This allows you to load the user's profile and provide a personalized experience from the first message.
- CONTRADICTION HANDLING: If a user provides new info that conflicts with old info, use the `update_user_info` tool (if available) to overwrite the existing key with the new value.
- PRIVACY: If a user asks to "forget" or "delete" something, use the `delete_user_info` tool (if available).

# EXAMPLES OF TOOL USE (IF TOOLS ARE ENABLED)

Example 1: Learning New Info
User: "I'm training for a marathon and my knees are killing me."
Action: update_user_info(key="current_activity", value="Training for a marathon", category="interests")
Action: update_user_info(key="health_note", value="Knee pain from running", category="bio")
Response: "I've noted that you're training for a marathon! Sorry to hear about the knee pain—make sure you're getting enough rest between runs."

Example 2: Recalling Family Info
User: "What should I get my sister for her birthday?"
Action: get_user_info(category="family")
(Result: { "sister_name": "Sarah", "sister_interests": "Photography, Hiking" })
Response: "Since Sarah loves photography and hiking, maybe a high-quality weather-proof camera strap or a National Parks pass would be a great gift?"

Example 3: Updating Preferences
User: "I've actually decided to go vegan."
Action: update_user_info(key="dietary_pref", value="Vegan", category="preferences")
Response: "Got it. I've updated your profile to 'Vegan.' I'll make sure all future recipe or restaurant suggestions reflect that!"

Example 4: Deleting Info
User: "Stop tracking my location, I don't live in Fishers anymore."
Action: delete_user_info(key="location")
Response: "No problem. I've removed your location from my records."
"""
            sys_content += "\n\n" + memory_instructions.strip()
            
        # 4. Attachment Instructions
        if has_attachments:
            sys_content += "\n\nYou have been provided with external documents. Always prioritize information found in the <file_attachment> tags over your general training data if there is a conflict. If the answer isn't in the file, explicitly state that."
            
        # 5. Tool Usage Instructions
        if tool_funcs_map or has_tools:
            from utils.config import config_manager
            sys_content += "\n\n" + config_manager.get_tool_system_prompt()
            
        return sys_content

system_message_service = SystemMessageService()
