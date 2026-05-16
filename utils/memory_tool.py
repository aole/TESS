import json
import os
from pathlib import Path

# Setup data directory and file path
DATA_DIR = Path("data")
MEMORY_FILE = DATA_DIR / "user_memory.json"

def _load_memory() -> dict:
    """Helper to load the memory file or return an empty dict if not found."""
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    if not MEMORY_FILE.exists():
        return {}
    
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_memory(data: dict):
    """Helper to write the current memory state to the JSON file."""
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)

def update_user_info(key: str, value: str, category: str) -> dict:
    """
    Saves or updates a specific piece of user information in long-term memory.
    
    This tool should be used whenever the user provides personal details like 
    their name, age, family relations, interests, or specific preferences.
    
    Args:
        key (str): The specific attribute name (e.g., "sister_name", "favorite_color").
        value (str): The information to be stored.
        category (str): The bucket for this info. Must be one of: 
                        ['bio', 'family', 'interests', 'preferences'].
    
    Returns:
        dict: A confirmation of the update or an error message.
    """
    try:
        memory = _load_memory()
        
        if category not in memory:
            memory[category] = {}
        
        memory[category][key] = value
        _save_memory(memory)
        
        return {"status": "success", "message": f"Updated {key} in {category}."}
    except Exception as e:
        return {"error": f"Failed to update user info: {str(e)}"}

def get_user_info(category: str = None) -> dict:
    """
    Retrieves stored information about the user to provide personalized context.
    
    Use this at the start of a conversation or when context is needed to 
    answer a personal question.
    
    Args:
        category (str, optional): The category to retrieve ('bio', 'family', 
                                 'interests', 'preferences'). If None, returns all.
                                 
    Returns:
        dict: The requested user data or an empty dict if not found.
    """
    try:
        memory = _load_memory()
        if category:
            return memory.get(category, {})
        return memory
    except Exception as e:
        return {"error": f"Failed to retrieve user info: {str(e)}"}

def delete_user_info(key: str) -> dict:
    """
    Removes a specific piece of information from the user's memory.
    
    Use this when a user explicitly asks to "forget" a detail or if 
    information is no longer relevant.
    
    Args:
        key (str): The specific attribute name to delete.
        
    Returns:
        dict: A confirmation of deletion or an error if the key wasn't found.
    """
    try:
        memory = _load_memory()
        found = False
        
        for category in memory:
            if key in memory[category]:
                del memory[category][key]
                found = True
                break
        
        if found:
            _save_memory(memory)
            return {"status": "success", "message": f"Deleted '{key}' from memory."}
        else:
            return {"error": f"Key '{key}' not found in any category."}
            
    except Exception as e:
        return {"error": f"Failed to delete user info: {str(e)}"}
