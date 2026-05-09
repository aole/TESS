import os
import json

def get_app_data_dir(app_name):
    """
    Returns the path to a dedicated data directory for the app.
    It stores data in data/apps/<app_name> to keep it centralized within the main data folder.
    """
    data_dir = os.path.join(os.getcwd(), 'data', 'apps', app_name)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def load_app_data(app_name, filename, default_data=None):
    """
    Loads JSON data for the given app.
    """
    file_path = os.path.join(get_app_data_dir(app_name), filename)
    if not os.path.exists(file_path):
        if default_data is not None:
            save_app_data(app_name, filename, default_data)
        return default_data
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default_data

def save_app_data(app_name, filename, data):
    """
    Saves JSON data for the given app.
    """
    file_path = os.path.join(get_app_data_dir(app_name), filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

_badge_update_callbacks = []

def register_badge_update_callback(callback):
    """
    Registers a callback to be called when any app's badge is updated.
    """
    if callback not in _badge_update_callbacks:
        _badge_update_callbacks.append(callback)

def set_app_badge(app_name, count):
    """
    Sets a badge count for the app to be displayed in the sidebar.
    """
    badges = load_app_data('system', 'badges.json', default_data={})
    badges[app_name] = count
    save_app_data('system', 'badges.json', badges)
    
    for cb in _badge_update_callbacks.copy():
        try:
            cb()
        except Exception:
            if cb in _badge_update_callbacks:
                _badge_update_callbacks.remove(cb)

def get_app_badge(app_name):
    """
    Gets the current badge count for the app.
    """
    badges = load_app_data('system', 'badges.json', default_data={})
    return badges.get(app_name, 0)
