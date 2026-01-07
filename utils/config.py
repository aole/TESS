import json
import os
from typing import Dict, Any

CONFIG_PATH = os.path.join(os.getcwd(), 'config.json')

DEFAULT_CONFIG = {
    "logging": {
        "chat": True,
        "arena": True,
        "batch": True
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

config_manager = ConfigManager()
