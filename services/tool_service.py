import os
import ast
import glob
import re
from dataclasses import dataclass, asdict
from typing import List, Optional

TOOLS_DIR = 'data/tools'

@dataclass
class Tool:
    name: str  # Filename without extension
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
        self._ensure_tools_dir()

    def _ensure_tools_dir(self):
        os.makedirs(TOOLS_DIR, exist_ok=True)

    def _parse_tool_file(self, file_path: str) -> Optional[Tool]:
        try:
            filename = os.path.basename(file_path)
            name = os.path.splitext(filename)[0]
            
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            try:
                tree = ast.parse(code)
                description = ast.get_docstring(tree) or ""
                
                # Check for __active__ variable
                active = True
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == '__active__':
                                if isinstance(node.value, ast.Constant): # python 3.8+
                                    active = bool(node.value.value)
                                elif isinstance(node.value, ast.NameConstant): # python < 3.8
                                    active = bool(node.value.value)
                                break
            except SyntaxError:
                # If code is invalid, still return it but maybe mark it? 
                # For now we just return what we can
                description = "Syntax Error in file"
                active = True

            return Tool(name=name, description=description, code=code, active=active)
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
        return tools

    def get_tool(self, name: str) -> Optional[Tool]:
        file_path = os.path.join(TOOLS_DIR, f"{name}.py")
        if os.path.exists(file_path):
            return self._parse_tool_file(file_path)
        return None

    def create_tool(self, tool: Tool) -> bool:
        file_path = os.path.join(TOOLS_DIR, f"{tool.name}.py")
        if os.path.exists(file_path):
            return False
        
        return self._write_tool_file(file_path, tool.code, tool.active)

    def _write_tool_file(self, file_path: str, code: str, active: bool) -> bool:
        try:
            # Check if we need to insert or update __active__
            has_active = re.search(r'^__active__\s*=', code, re.MULTILINE)
            
            if has_active:
                # Replace existing
                new_line = f"__active__ = {active}"
                code = re.sub(r'^__active__\s*=.*$', new_line, code, flags=re.MULTILINE)
            else:
                # Append if not True (since default is True)
                if not active:
                    if not code.endswith('\n'):
                        code += '\n'
                    code += f"\n__active__ = {active}\n"
            
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
            
        return self._write_tool_file(original_path, updated_tool.code, updated_tool.active)

    def delete_tool(self, name: str) -> bool:
        file_path = os.path.join(TOOLS_DIR, f"{name}.py")
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    def toggle_tool_active(self, name: str) -> bool:
        tool = self.get_tool(name)
        if tool:
            tool.active = not tool.active
            return self._write_tool_file(os.path.join(TOOLS_DIR, f"{name}.py"), tool.code, tool.active)
        return False

tool_service = ToolService()
