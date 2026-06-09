from core.config.settings_service import settings_service


DEFAULT_SETTINGS = {
    "theme": {
        "value": "dark",
        "type": "str",
        "category": "ui",
        "description": "Default UI theme",
    },
    "media_root": {
        "value": "output",
        "type": "str",
        "category": "storage",
        "description": "Root folder for generated media",
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
        "description": "Default output image format",
    },
    "auto_save_images": {
        "value": True,
        "type": "bool",
        "category": "storage",
        "description": "Automatically save generated images",
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
