# NiceGUI Cheatsheet

- **from nicegui import ui** - Import the NiceGUI UI toolkit to build pages and components.
- **@ui.page("/path")** - Register a function as a page route.
- **ui.label("Hello")** - Render a simple text label.
- **ui.button("Click", on_click=...)** - Create a button and attach a click handler.
- **ui.row()** - Lay out children horizontally in a row.
- **ui.column()** - Lay out children vertically in a column.
- **ui.notify("Saved")** - Show a temporary notification to the user.
- **ui.dialog()** - Create a modal dialog for focused interactions.
