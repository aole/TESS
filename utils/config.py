import json
import os
from typing import Dict, Any

CONFIG_PATH = os.path.join(os.getcwd(), 'config.json')

DEFAULT_CONFIG = {
    "logging": {
        "chat": True,
        "batch": True
    },
    "audio": {
        "auto_start": True
    }
}

class ConfigManager:
    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(CONFIG_PATH):
            self._save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        try:
            with open(CONFIG_PATH, 'r') as f:
                loaded = json.load(f)
                # Ensure structure exists
                if "logging" not in loaded:
                    loaded["logging"] = DEFAULT_CONFIG["logging"]
                return loaded
        except Exception:
            return DEFAULT_CONFIG

    def _save_config(self, config: Dict[str, Any]):
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)

    def set_logging(self, section: str, enabled: bool):
        if "logging" not in self.config:
            self.config["logging"] = {}
        self.config["logging"][section] = enabled
        self._save_config(self.config)

    def is_logging_enabled(self, section: str) -> bool:
        return self.config.get("logging", {}).get(section, True)

    def is_tool_active(self, tool_name: str) -> bool:
        return tool_name not in self.config.get("inactive_tools", [])

    def set_tool_active(self, tool_name: str, active: bool):
        inactive_tools = self.config.get("inactive_tools", [])
        # Ensure it's a list (in case of malformed config)
        if not isinstance(inactive_tools, list):
            inactive_tools = []

        if active:
            if tool_name in inactive_tools:
                inactive_tools.remove(tool_name)
        else:
            if tool_name not in inactive_tools:
                inactive_tools.append(tool_name)
        
        self.config["inactive_tools"] = inactive_tools
        self._save_config(self.config)

    def get_rating_tags(self) -> list:
        return self.config.get("rating_tags", ["General", "Coding", "Tools", "Writing"])

    def set_rating_tags(self, tags: list):
        self.config["rating_tags"] = tags
        self._save_config(self.config)

    def add_rating_tag(self, tag: str):
        tags = self.get_rating_tags()
        if tag not in tags:
            tags.append(tag)
            self.set_rating_tags(tags)

    def remove_rating_tag(self, tag: str):
        tags = self.get_rating_tags()
        if tag in tags:
            tags.remove(tag)
            self.set_rating_tags(tags)

    def get_note_categories(self) -> list:
        return self.config.get("note_categories", ["General", "Work", "Home"])

    def set_note_categories(self, categories: list):
        self.config["note_categories"] = categories
        self._save_config(self.config)

    def add_note_category(self, category: str):
        categories = self.get_note_categories()
        if category not in categories:
            categories.append(category)
            self.set_note_categories(categories)

    def remove_note_category(self, category: str):
        categories = self.get_note_categories()
        if category in categories:
            categories.remove(category)
            self.set_note_categories(categories)

    def get_note_storage(self) -> str:
        return self.config.get("note_storage", "local")

    def set_note_storage(self, storage_type: str):
        self.config["note_storage"] = storage_type
        self._save_config(self.config)

    def get_last_notes_sync(self) -> str:
        """Return ISO timestamp of the last successful notes sync, or empty string."""
        return self.config.get("last_notes_sync", "")

    def set_last_notes_sync(self, iso_timestamp: str):
        self.config["last_notes_sync"] = iso_timestamp
        self._save_config(self.config)

    def get_tts_voice(self) -> str:
        return self.config.get("audio", {}).get("voice", "af_heart")

    def set_tts_voice(self, voice: str):
        if "audio" not in self.config:
            self.config["audio"] = {}
        self.config["audio"]["voice"] = voice
        self._save_config(self.config)

    def is_tts_enabled(self) -> bool:
        return self.config.get("audio", {}).get("enabled", False)

    def set_tts_enabled(self, enabled: bool):
        if "audio" not in self.config:
            self.config["audio"] = {}
        self.config["audio"]["enabled"] = enabled
        self._save_config(self.config)

    def get_tool_system_prompt(self) -> str:
        default_prompt = "IMPORTANT: When generating tool calls, ensure strictly valid JSON. Do not use invalid escape sequences like '\\?' inside strings. Only escape backslashes and double quotes. Note that the tool content/result is NOT displayed to the user, so you must interpret the tool content and provide the user a response based on it."
        return self.config.get("tool_system_prompt", default_prompt)

    def set_tool_system_prompt(self, prompt: str):
        self.config["tool_system_prompt"] = prompt
        self._save_config(self.config)

config_manager = ConfigManager()
