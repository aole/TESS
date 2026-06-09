import json
from typing import Any

from core.db.connection import get_connection


class SettingsRepo:
    def _serialize_value(self, value: Any, value_type: str) -> str:
        if value_type == "json":
            return json.dumps(value)
        if value_type == "bool":
            return "1" if bool(value) else "0"
        return str(value)

    def _deserialize_value(self, raw_value: str, value_type: str) -> Any:
        if value_type == "int":
            return int(raw_value)
        if value_type == "float":
            return float(raw_value)
        if value_type == "bool":
            return raw_value == "1"
        if value_type == "json":
            return json.loads(raw_value)
        return raw_value

    def _infer_value_type(self, value: Any) -> str:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, (dict, list)):
            return "json"
        return "str"

    def get(self, key: str, default: Any = None) -> Any:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value, value_type FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()

        if row is None:
            return default

        value, value_type = row
        return self._deserialize_value(value, value_type)

    def set(
        self,
        key: str,
        value: Any,
        value_type: str = "str",
        category: str | None = None,
        description: str | None = None,
    ) -> None:
        resolved_type = value_type
        if value_type == "str" and not isinstance(value, str):
            resolved_type = self._infer_value_type(value)

        serialized_value = self._serialize_value(value, resolved_type)

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, value_type, category, description, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    value_type = excluded.value_type,
                    category = excluded.category,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, serialized_value, resolved_type, category, description),
            )
            conn.commit()

    def get_all(self) -> dict[str, Any]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value, value_type, category, description, updated_at FROM app_settings ORDER BY key"
            ).fetchall()

        return {
            key: {
                "value": self._deserialize_value(value, value_type),
                "value_type": value_type,
                "category": category,
                "description": description,
                "updated_at": updated_at,
            }
            for key, value, value_type, category, description, updated_at in rows
        }

    def get_by_category(self, category: str) -> dict[str, Any]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT key, value, value_type, category, description, updated_at
                FROM app_settings
                WHERE category = ?
                ORDER BY key
                """,
                (category,),
            ).fetchall()

        return {
            key: {
                "value": self._deserialize_value(value, value_type),
                "value_type": value_type,
                "category": category,
                "description": description,
                "updated_at": updated_at,
            }
            for key, value, value_type, category, description, updated_at in rows
        }

    def delete(self, key: str) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
            conn.commit()


settings_repo = SettingsRepo()
