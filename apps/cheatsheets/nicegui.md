# NiceGUI Cheatsheet

A compact reference for building Python-based web UIs with [NiceGUI](https://nicegui.io).

---

## 1. Basic App Structure

```python
from nicegui import ui

ui.label('Hello, NiceGUI!')

ui.run()
```

| Command                             | Purpose                                  |
| ----------------------------------- | ---------------------------------------- |
| `from nicegui import ui`            | Import the main NiceGUI UI toolkit.      |
| `ui.run()`                          | Start the NiceGUI web server.            |
| `ui.run(host='0.0.0.0', port=8080)` | Run the app on a specific host and port. |
| `ui.run(reload=False)`              | Disable auto-reload during development.  |

---

## 2. Pages and Routes

```python
from nicegui import ui

@ui.page('/')
def home():
    ui.label('Home Page')

@ui.page('/settings')
def settings():
    ui.label('Settings Page')

ui.run()
```

| Command                    | Purpose                               |
| -------------------------- | ------------------------------------- |
| `@ui.page('/')`            | Register a function as a page route.  |
| `@ui.page('/path')`        | Create a custom route.                |
| `@ui.page('/user/{name}')` | Create a route with a path parameter. |

Example:

```python
@ui.page('/user/{name}')
def user_page(name: str):
    ui.label(f'Hello {name}')
```

---

## 3. Text and Display Elements

```python
ui.label('Simple text')
ui.markdown('**Bold Markdown**')
ui.html('<b>Raw HTML</b>')
```

| Element                                   | Purpose                                |
| ----------------------------------------- | -------------------------------------- |
| `ui.label('Text')`                        | Display simple text.                   |
| `ui.markdown('...')`                      | Render Markdown content.               |
| `ui.html('...')`                          | Render raw HTML.                       |
| `ui.link('Google', 'https://google.com')` | Create a clickable link.               |
| `ui.separator()`                          | Add a horizontal divider.              |
| `ui.space()`                              | Add flexible spacing between elements. |

---

## 4. Buttons and Actions

```python
def save():
    ui.notify('Saved!')

ui.button('Save', on_click=save)
```

| Command                               | Purpose                 |
| ------------------------------------- | ----------------------- |
| `ui.button('Click')`                  | Create a button.        |
| `ui.button('Save', on_click=handler)` | Attach a click handler. |
| `button.disable()`                    | Disable a button.       |
| `button.enable()`                     | Enable a button.        |
| `button.set_text('New Text')`         | Change button text.     |

Async handler example:

```python
async def load_data():
    ui.notify('Loading...')

ui.button('Load', on_click=load_data)
```

---

## 5. Layout Elements

```python
with ui.row():
    ui.label('Left')
    ui.label('Right')

with ui.column():
    ui.label('Top')
    ui.label('Bottom')
```

| Layout                  | Purpose                        |
| ----------------------- | ------------------------------ |
| `ui.row()`              | Arrange children horizontally. |
| `ui.column()`           | Arrange children vertically.   |
| `ui.grid(columns=3)`    | Arrange children in a grid.    |
| `ui.card()`             | Create a card-style container. |
| `ui.expansion('Title')` | Create collapsible content.    |
| `ui.tabs()`             | Create tab navigation.         |
| `ui.splitter()`         | Create resizable split panels. |

Example:

```python
with ui.card().classes('w-full max-w-md'):
    ui.label('Card Title').classes('text-lg font-bold')
    ui.label('Card content goes here.')
```

---

## 6. Inputs and Forms

```python
name = ui.input('Name')
age = ui.number('Age')
active = ui.checkbox('Active')
```

| Element                      | Purpose                 |
| ---------------------------- | ----------------------- |
| `ui.input('Name')`           | Text input.             |
| `ui.textarea('Description')` | Multi-line text input.  |
| `ui.number('Age')`           | Numeric input.          |
| `ui.checkbox('Enabled')`     | Boolean checkbox.       |
| `ui.switch('Dark Mode')`     | Toggle switch.          |
| `ui.select([...])`           | Dropdown select.        |
| `ui.radio([...])`            | Radio-button selection. |
| `ui.slider(min=0, max=100)`  | Slider input.           |
| `ui.upload()`                | File upload input.      |

Example:

```python
name = ui.input('Name', placeholder='Enter your name')
ui.button('Submit', on_click=lambda: ui.notify(f'Hello {name.value}'))
```

---

## 7. Input Validation

```python
ui.input(
    'Username',
    validation=lambda value: 'Too short' if len(value) < 3 else None,
)
```

Dictionary-style validation:

```python
ui.input(
    'Password',
    validation={
        'Must be at least 8 characters': lambda value: len(value) >= 8,
        'Must contain a number': lambda value: any(c.isdigit() for c in value),
    },
)
```

---

## 8. Notifications and Dialogs

```python
ui.notify('Saved successfully')
```

| Command                               | Purpose                        |
| ------------------------------------- | ------------------------------ |
| `ui.notify('Message')`                | Show a temporary notification. |
| `ui.notify('Error', type='negative')` | Show an error notification.    |
| `ui.dialog()`                         | Create a modal dialog.         |
| `dialog.open()`                       | Open a dialog.                 |
| `dialog.close()`                      | Close a dialog.                |

Dialog example:

```python
with ui.dialog() as dialog, ui.card():
    ui.label('Are you sure?')
    with ui.row():
        ui.button('Cancel', on_click=dialog.close)
        ui.button('OK', on_click=lambda: ui.notify('Confirmed'))

ui.button('Open Dialog', on_click=dialog.open)
```

---

## 9. Styling with Classes, Props, and Styles

NiceGUI works well with Tailwind-style utility classes.

```python
ui.label('Title').classes('text-2xl font-bold text-blue-600')
ui.button('Save').props('color=primary')
ui.card().style('width: 300px; padding: 16px;')
```

| Method                       | Purpose                                          |
| ---------------------------- | ------------------------------------------------ |
| `.classes('...')`            | Add CSS/Tailwind classes.                        |
| `.props('...')`              | Add Quasar component props.                      |
| `.style('...')`              | Add inline CSS styles.                           |
| `.bind_visibility_from(...)` | Bind visibility to another value.                |
| `.bind_value(...)`           | Bind component value to another object/property. |

Common classes:

```python
.classes('w-full')
.classes('max-w-md')
.classes('p-4')
.classes('m-2')
.classes('gap-4')
.classes('items-center')
.classes('justify-between')
.classes('text-lg font-bold')
```

---

## 10. Colors and Dark Mode

```python
ui.colors(primary='#2563eb')
```

Dark mode:

```python
dark = ui.dark_mode()
ui.switch('Dark Mode').bind_value(dark)
```

| Command                        | Purpose                 |
| ------------------------------ | ----------------------- |
| `ui.colors(primary='#2563eb')` | Set theme colors.       |
| `ui.dark_mode()`               | Control page dark mode. |
| `ui.dark_mode(True)`           | Force dark mode on.     |
| `ui.dark_mode(False)`          | Force light mode.       |
| `ui.dark_mode(None)`           | Use system preference.  |

---

## 11. Tables

```python
columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'age', 'label': 'Age', 'field': 'age'},
]

rows = [
    {'name': 'Alice', 'age': 30},
    {'name': 'Bob', 'age': 25},
]

ui.table(columns=columns, rows=rows)
```

Useful for:

* Search results
* Admin screens
* Data previews
* CRUD-style interfaces

---

## 12. Images and Media

```python
ui.image('image.png')
ui.audio('audio.mp3')
ui.video('video.mp4')
```

| Element                 | Purpose           |
| ----------------------- | ----------------- |
| `ui.image(path_or_url)` | Display an image. |
| `ui.audio(path_or_url)` | Play audio.       |
| `ui.video(path_or_url)` | Play video.       |
| `ui.icon('home')`       | Display an icon.  |

Image styling example:

```python
ui.image('cat.png').classes('w-64 rounded-lg shadow')
```

---

## 13. Events

Most elements have built-in event parameters, such as `on_click`, `on_change`, or `on_value_change`.

```python
ui.button('Click', on_click=lambda: ui.notify('Clicked'))
ui.input('Name', on_change=lambda e: ui.notify(e.value))
```

Generic event handler:

```python
ui.button('Hover Me').on(
    'mouseover',
    lambda: ui.notify('Mouse over')
)
```

Use throttling for high-frequency events:

```python
ui.label('Move mouse here').on(
    'mousemove',
    lambda e: print(e.args),
    throttle=0.5,
)
```

---

## 14. Timers and Refreshing UI

```python
counter = ui.label('0')

count = 0

def update():
    global count
    count += 1
    counter.set_text(str(count))

ui.timer(1.0, update)
```

| Command                       | Purpose                                       |
| ----------------------------- | --------------------------------------------- |
| `ui.timer(seconds, callback)` | Run a callback repeatedly.                    |
| `element.set_text('...')`     | Update label/button text.                     |
| `element.update()`            | Refresh an element after changing properties. |
| `element.delete()`            | Remove an element from the UI.                |

---

## 15. Refreshable Sections

Use `@ui.refreshable` when part of the UI needs to be rebuilt.

```python
items = ['Apple', 'Banana']

@ui.refreshable
def item_list():
    for item in items:
        ui.label(item)

item_list()

def add_item():
    items.append('Orange')
    item_list.refresh()

ui.button('Add Item', on_click=add_item)
```

---

## 16. Client Storage and App Storage

```python
from nicegui import app, ui

@ui.page('/')
def index():
    ui.input('Note').bind_value(app.storage.user, 'note')

ui.run(storage_secret='your-secret-key')
```

| Storage               | Purpose                      |
| --------------------- | ---------------------------- |
| `app.storage.user`    | Persistent per-user storage. |
| `app.storage.browser` | Browser-specific storage.    |
| `app.storage.general` | Shared app-wide storage.     |
| `app.storage.tab`     | Per-browser-tab storage.     |

---

## 17. Running JavaScript

```python
ui.run_javascript('alert("Hello from JavaScript")')
```

Example:

```python
async def get_width():
    width = await ui.run_javascript('window.innerWidth')
    ui.notify(f'Width: {width}')

ui.button('Get Width', on_click=get_width)
```

---

## 18. Navigation

```python
ui.link('Go to Settings', '/settings')
```

Programmatic navigation:

```python
ui.navigate.to('/settings')
ui.navigate.back()
```

External link:

```python
ui.link('NiceGUI Docs', 'https://nicegui.io')
```

---

## 19. Common CRUD Pattern

```python
items = []

name_input = ui.input('Item name')

def add_item():
    if name_input.value:
        items.append(name_input.value)
        name_input.value = ''
        item_list.refresh()

@ui.refreshable
def item_list():
    for item in items:
        with ui.row().classes('items-center gap-2'):
            ui.label(item)
            ui.button('Delete', on_click=lambda item=item: delete_item(item))

def delete_item(item):
    items.remove(item)
    item_list.refresh()

ui.button('Add', on_click=add_item)
item_list()
```

---

## 20. Common Page Skeleton

```python
from nicegui import ui

@ui.page('/')
def index():
    ui.dark_mode().enable()

    with ui.header().classes('items-center justify-between'):
        ui.label('My App').classes('text-xl font-bold')
        ui.button('Settings', on_click=lambda: ui.navigate.to('/settings'))

    with ui.left_drawer():
        ui.link('Home', '/')
        ui.link('Settings', '/settings')

    with ui.column().classes('w-full max-w-4xl mx-auto p-4 gap-4'):
        ui.label('Dashboard').classes('text-2xl font-bold')

        with ui.card().classes('w-full'):
            ui.label('Main content goes here.')

ui.run()
```

---

## 21. Quick Reference

| Task           | Code                               |
| -------------- | ---------------------------------- |
| Import NiceGUI | `from nicegui import ui`           |
| Start app      | `ui.run()`                         |
| Create page    | `@ui.page('/path')`                |
| Text           | `ui.label('Hello')`                |
| Button         | `ui.button('Click', on_click=...)` |
| Input          | `ui.input('Name')`                 |
| Row layout     | `with ui.row(): ...`               |
| Column layout  | `with ui.column(): ...`            |
| Card           | `with ui.card(): ...`              |
| Dialog         | `with ui.dialog() as dialog: ...`  |
| Notification   | `ui.notify('Saved')`               |
| Image          | `ui.image('file.png')`             |
| Table          | `ui.table(columns=..., rows=...)`  |
| Timer          | `ui.timer(1.0, callback)`          |
| Dark mode      | `ui.dark_mode()`                   |
| Navigate       | `ui.navigate.to('/path')`          |
| Add classes    | `.classes('p-4 text-lg')`          |
| Add props      | `.props('color=primary')`          |
| Add CSS        | `.style('width: 300px')`           |

---

## 22. Practical Tips

* Use `with ui.row()` and `with ui.column()` for most layouts.
* Use `.classes()` heavily for spacing, sizing, and responsive design.
* Use `ui.card()` to visually group related content.
* Use `ui.notify()` for quick feedback after user actions.
* Use `ui.dialog()` for confirmations, forms, and focused interactions.
* Use `@ui.refreshable` when a UI section needs to be rebuilt.
* Use `ui.timer()` carefully; avoid very short intervals unless necessary.
* For large lists or image grids, consider pagination, lazy loading, thumbnails, or virtual scrolling.
* Keep long-running work async or move it into background tasks so the UI does not freeze.
* Use `app.storage.user` for simple per-user persistence.
