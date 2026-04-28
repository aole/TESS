import json
import os
from typing import Dict, Any

CONFIG_PATH = os.path.join(os.getcwd(), 'config.json')

DEFAULT_CONFIG = {
    "logging": {
        "chat": True,
        "arena": True,
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

    def get_default_model(self, key: str) -> str:
        return self.config.get("default_models", {}).get(key, "")

    def set_default_model(self, key: str, model_name: str):
        if "default_models" not in self.config:
            self.config["default_models"] = {}
        self.config["default_models"][key] = model_name
        self._save_config(self.config)

    def get_auto_start_audio(self) -> bool:
        return self.config.get("audio", {}).get("auto_start", True)

    def set_auto_start_audio(self, auto_start: bool):
        if "audio" not in self.config:
            self.config["audio"] = {}
        self.config["audio"]["auto_start"] = auto_start
        self._save_config(self.config)

config_manager = ConfigManager()
