from core.config.settings_service import settings_service


DEFAULT_SETTINGS = {
    "theme": {
        "value": "dark",
        "type": "str",
        "category": "ui",
        "description": "Default UI theme",
    },
    "default_width": {
        "value": 1024,
        "type": "int",
        "category": "generation",
        "description": "Default image width",
    },
    "default_height": {
        "value": 1024,
        "type": "int",
        "category": "generation",
        "description": "Default image height",
    },
    "default_steps": {
        "value": 20,
        "type": "int",
        "category": "generation",
        "description": "Default generation steps",
    },
    "thumbnail_size": {
        "value": 256,
        "type": "int",
        "category": "storage",
        "description": "Thumbnail size in pixels",
    },
}


def seed_default_settings() -> None:
    for key, meta in DEFAULT_SETTINGS.items():
        existing_value = settings_service.get(key, default=None)
        if existing_value is not None:
            continue

        settings_service.set(
            key=key,
            value=meta["value"],
            value_type=meta["type"],
            category=meta.get("category"),
            description=meta.get("description"),
        )
