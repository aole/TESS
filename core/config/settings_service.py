from typing import Any

from core.db.settings_repo import settings_repo


class SettingsService:
    def get(self, key: str, default: Any = None) -> Any:
        return settings_repo.get(key, default=default)

    def set(
        self,
        key: str,
        value: Any,
        value_type: str = "str",
        category: str | None = None,
        description: str | None = None,
    ) -> None:
        settings_repo.set(
            key=key,
            value=value,
            value_type=value_type,
            category=category,
            description=description,
        )

    def get_all(self) -> dict[str, Any]:
        return settings_repo.get_all()

    def get_by_category(self, category: str) -> dict[str, Any]:
        return settings_repo.get_by_category(category)

    def delete(self, key: str) -> None:
        settings_repo.delete(key)


settings_service = SettingsService()
