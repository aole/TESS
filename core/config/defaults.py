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
    "default_cfg": {
        "value": 4.0,
        "type": "float",
        "category": "generation",
        "description": "Default CFG scale",
    },
    "default_seed_mode": {
        "value": "random",
        "type": "str",
        "category": "generation",
        "description": "Default seed mode",
    },
    "default_output_format": {
        "value": "png",
        "type": "str",
        "category": "generation",
        "description": "Default image format",
    },
    "thumbnail_size": {
        "value": 256,
        "type": "int",
        "category": "storage",
        "description": "Thumbnail size in pixels",
    },
    "thumbnail_format": {
        "value": "webp",
        "type": "str",
        "category": "storage",
        "description": "Thumbnail output format",
    },
    "default_story_processing_model": {
        "value": None,
        "type": "json",
        "category": "default_models",
        "description": "Default model used for story processing",
    },
    "default_vision_model": {
        "value": None,
        "type": "json",
        "category": "default_models",
        "description": "Default model used for vision tasks",
    },
}


def seed_default_settings() -> None:
    for key, meta in DEFAULT_SETTINGS.items():
        if settings_service.exists(key):
            continue

        settings_service.set(
            key=key,
            value=meta["value"],
            value_type=meta["type"],
            category=meta.get("category"),
            description=meta.get("description"),
        )
