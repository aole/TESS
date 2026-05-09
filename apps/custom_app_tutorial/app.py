from nicegui import ui

def render():
    with ui.column().classes('w-full max-w-3xl mx-auto mt-8 gap-6'):
        ui.label('Custom Apps Tutorial').classes('text-3xl font-bold text-indigo-400')
        
        ui.markdown('''
This page demonstrates how to create and integrate custom apps into the system.

### Creating a New App

1. **Create a Folder:** Navigate to the `apps` directory in the root of the project and create a new folder for your app (e.g., `my_cool_app`).
2. **Create `app.py`:** Inside your new folder, create a file named `app.py`.
3. **Define `render()`:** In `app.py`, define a function named `render()`. This function will be called to build your app's UI using NiceGUI.

### Example `app.py`

```python
from nicegui import ui
from apps.utils import load_app_data, save_app_data

def render():
    ui.label('Hello from my custom app!').classes('text-2xl font-bold')
    ui.button('Click me', on_click=lambda: ui.notify('Button clicked!'))
```

### Storing Data

If your custom app needs to save user data, you should use the provided utilities to ensure it is gitignored and centralized:

```python
from apps.utils import load_app_data, save_app_data

# Load data (creates file with default if it doesn't exist)
data = load_app_data('my_app_name', 'data.json', default_data={"key": "value"})

# Save data
save_app_data('my_app_name', 'data.json', data)
```
Data will be stored safely in `data/apps/my_app_name/`.

### App Badges

You can display a real-time notification badge (a small red number) next to your app's name in the sidebar. This is useful for things like "tasks left today" or "unread messages".

```python
from apps.utils import set_app_badge, get_app_badge

# Set a badge count for your app (this instantly updates the sidebar)
set_app_badge('my_app_name', 3)

# Retrieve the current badge count
current_count = get_app_badge('my_app_name')
```

### How it Works

The system automatically scans the `apps` folder. Each folder is treated as a separate application. When you click an app on the left panel, the system dynamically loads the `app.py` from that app's folder and executes its `render()` function to display the content.
        ''').classes('text-base text-gray-300 leading-relaxed')
