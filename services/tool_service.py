import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional

DATA_FILE = 'data/tools.json'

@dataclass
class Tool:
    name: str
    description: str
    code: str
    active: bool = True

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        return Tool(**data)

class ToolService:
    def __init__(self):
        self._ensure_data_file()

    def _ensure_data_file(self):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        if not os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'w') as f:
                json.dump([], f)

    def get_all_tools(self) -> List[Tool]:
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                return [Tool.from_dict(item) for item in data]
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_tools(self, tools: List[Tool]):
        with open(DATA_FILE, 'w') as f:
            json.dump([t.to_dict() for t in tools], f, indent=2)

    def get_tool(self, name: str) -> Optional[Tool]:
        tools = self.get_all_tools()
        for tool in tools:
            if tool.name == name:
                return tool
        return None

    def create_tool(self, tool: Tool) -> bool:
        tools = self.get_all_tools()
        if any(t.name == tool.name for t in tools):
            return False
        tools.append(tool)
        self.save_tools(tools)
        return True

    def update_tool(self, original_name: str, updated_tool: Tool) -> bool:
        tools = self.get_all_tools()
        for i, t in enumerate(tools):
            if t.name == original_name:
                # Check for name collision if name is changed
                if original_name != updated_tool.name and any(x.name == updated_tool.name for x in tools):
                    return False
                tools[i] = updated_tool
                self.save_tools(tools)
                return True
        return False

    def delete_tool(self, name: str) -> bool:
        tools = self.get_all_tools()
        original_len = len(tools)
        tools = [t for t in tools if t.name != name]
        if len(tools) < original_len:
            self.save_tools(tools)
            return True
        return False

    def toggle_tool_active(self, name: str) -> bool:
        tools = self.get_all_tools()
        for t in tools:
            if t.name == name:
                t.active = not t.active
                self.save_tools(tools)
                return True
        return False

tool_service = ToolService()
