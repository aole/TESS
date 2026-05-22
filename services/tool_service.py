import os
import ast
import glob
from dataclasses import dataclass, asdict
from typing import List, Optional

from utils.config import config_manager

TOOLS_DIR = 'data/tools'

@dataclass
class Tool:
    name: str  # Filename without extension
    description: str
    code: str
    active: bool = True
    is_builtin: bool = False
    has_error: bool = False

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        return Tool(**data)

class ToolService:
    def __init__(self):
        self._ensure_tools_dir()

    def _ensure_tools_dir(self):
        os.makedirs(TOOLS_DIR, exist_ok=True)

    def _parse_tool_file(self, file_path: str) -> Optional[Tool]:
        try:
            filename = os.path.basename(file_path)
            name = os.path.splitext(filename)[0]
            
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            has_error = False
            try:
                tree = ast.parse(code)
                description = ast.get_docstring(tree) or ""
            except SyntaxError:
                description = "Syntax Error in file"
                has_error = True

            # Active status is now managed by config
            active = config_manager.is_tool_active(name)
            
            return Tool(name=name, description=description, code=code, active=active, has_error=has_error)
        except Exception as e:
            print(f"Error parsing tool {file_path}: {e}")
            return None

    def get_all_tools(self) -> List[Tool]:
        tools = []
        pattern = os.path.join(TOOLS_DIR, "*.py")
        for file_path in glob.glob(pattern):
            if os.path.basename(file_path) == "__init__.py":
                continue
            tool = self._parse_tool_file(file_path)
            if tool:
                tools.append(tool)
        
        # Add builtin tools
        tools.extend(self.get_builtin_tools())
        
        return tools

    def get_builtin_tools(self) -> List[Tool]:
        builtin = []
        
        # Visual Tool
        visual_desc = "Generates an image using the Anima diffusion model. This model is specialized in producing high-quality anime-style images and illustrations."
        builtin.append(Tool(
            name="visual_tool",
            description=visual_desc,
            code="# Builtin Tool: visual_tool\n# (Implementation is in utils/visual_tool.py)",
            active=config_manager.is_tool_active("visual_tool"),
            is_builtin=True
        ))
        
        # Web Search Tool
        search_desc = "Search the web for a given query and return a cleaned summary. Also extract content from specific URLs."
        builtin.append(Tool(
            name="web_search_tool",
            description=search_desc,
            code="# Builtin Tool: web_search_tool\n# (Implementation is in utils/web_search_tool.py)",
            active=config_manager.is_tool_active("web_search_tool"),
            is_builtin=True
        ))

        # Memory Tool
        memory_desc = "Handles user long-term memory. Allows saving, retrieving, and deleting personal details about the user."
        builtin.append(Tool(
            name="user_memory_tool",
            description=memory_desc,
            code="# Builtin Tool: user_memory_tool\n# (Implementation is in utils/memory_tool.py)",
            active=config_manager.is_tool_active("user_memory_tool"),
            is_builtin=True
        ))
        
        return builtin

    def get_tool(self, name: str) -> Optional[Tool]:
        # Check builtin first
        for t in self.get_builtin_tools():
            if t.name == name:
                return t
        
        file_path = os.path.join(TOOLS_DIR, f"{name}.py")
        if os.path.exists(file_path):
            return self._parse_tool_file(file_path)
        return None

    def create_tool(self, tool: Tool) -> bool:
        file_path = os.path.join(TOOLS_DIR, f"{tool.name}.py")
        if os.path.exists(file_path):
            return False
        
        # Save code first so that invalid Python draft is stored and can be listed
        if self._write_tool_file(file_path, tool.code):
            # Save active status
            config_manager.set_tool_active(tool.name, tool.active)
            # Validate Python syntax and raise SyntaxError if invalid
            ast.parse(tool.code)
            return True
        return False

    def _write_tool_file(self, file_path: str, code: str) -> bool:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            return True
        except Exception as e:
            print(f"Error writing tool {file_path}: {e}")
            return False

    def update_tool(self, original_name: str, updated_tool: Tool) -> bool:
        original_path = os.path.join(TOOLS_DIR, f"{original_name}.py")
        new_path = os.path.join(TOOLS_DIR, f"{updated_tool.name}.py")
        
        # If the original file doesn't exist, we can't update it
        if not os.path.exists(original_path):
            return False

        if original_name != updated_tool.name:
            if os.path.exists(new_path):
                return False # Name collision
            os.rename(original_path, new_path)
            original_path = new_path
            # Clean up old config active status (reset to default/active by removing from inactive list)
            config_manager.set_tool_active(original_name, True)
            
        # Save code first so that invalid Python draft is stored and can be listed
        if self._write_tool_file(original_path, updated_tool.code):
            config_manager.set_tool_active(updated_tool.name, updated_tool.active)
            # Validate Python syntax and raise SyntaxError if invalid
            ast.parse(updated_tool.code)
            return True
        return False

    def delete_tool(self, name: str) -> bool:
        file_path = os.path.join(TOOLS_DIR, f"{name}.py")
        if os.path.exists(file_path):
            os.remove(file_path)
            # Cleanup config
            config_manager.set_tool_active(name, True)
            return True
        return False

    def toggle_tool_active(self, name: str) -> bool:
        tool = self.get_tool(name)
        if tool:
            new_active = not tool.active
            config_manager.set_tool_active(name, new_active)
            return True
        return False

tool_service = ToolService()
