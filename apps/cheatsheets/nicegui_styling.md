## NiceGUI Classes, Styles, and Props

### Basic Usage

| Method            | Use                                   |
| ----------------- | ------------------------------------- |
| `.classes('...')` | Add Tailwind / Quasar utility classes |
| `.style('...')`   | Add inline CSS                        |
| `.props('...')`   | Add Quasar component props            |
| `.tooltip('...')` | Add hover tooltip                     |

```python
ui.label('Hello').classes('text-xl font-bold')
ui.button('Save').props('color=primary rounded')
ui.card().style('width: 300px; padding: 16px;')
```

---

## Classes

Use `.classes()` for layout, spacing, sizing, colors, borders, and typography.

```python
ui.label('Title').classes('text-2xl font-bold text-blue-600')
```

### Spacing

| Class   | Use                  |
| ------- | -------------------- |
| `p-2`   | Padding              |
| `p-4`   | More padding         |
| `px-4`  | Horizontal padding   |
| `py-2`  | Vertical padding     |
| `m-2`   | Margin               |
| `mt-4`  | Top margin           |
| `mb-4`  | Bottom margin        |
| `gap-2` | Gap between children |
| `gap-4` | Larger gap           |

```python
with ui.column().classes('p-4 gap-4'):
    ui.label('One')
    ui.label('Two')
```

---

## Width and Height

| Class          | Use                        |
| -------------- | -------------------------- |
| `w-full`       | Full width                 |
| `w-1/2`        | Half width                 |
| `w-64`         | Fixed width                |
| `max-w-md`     | Medium max width           |
| `max-w-4xl`    | Large max width            |
| `h-full`       | Full height                |
| `h-screen`     | Full viewport height       |
| `min-h-screen` | Minimum full screen height |

```python
with ui.card().classes('w-full max-w-md'):
    ui.label('Login')
```

---

## Flex Layout

| Class             | Use                     |
| ----------------- | ----------------------- |
| `flex`            | Enable flexbox          |
| `flex-row`        | Horizontal direction    |
| `flex-col`        | Vertical direction      |
| `items-center`    | Align vertically center |
| `justify-center`  | Center horizontally     |
| `justify-between` | Space between items     |
| `flex-wrap`       | Wrap items              |
| `grow`            | Allow element to grow   |

```python
with ui.row().classes('w-full items-center justify-between'):
    ui.label('Title')
    ui.button('Save')
```

---

## Text

| Class           | Use              |
| --------------- | ---------------- |
| `text-sm`       | Small text       |
| `text-lg`       | Large text       |
| `text-xl`       | Extra large text |
| `text-2xl`      | Heading size     |
| `font-bold`     | Bold text        |
| `font-mono`     | Monospace text   |
| `text-center`   | Center text      |
| `text-gray-500` | Muted text       |
| `text-red-600`  | Red text         |

```python
ui.label('Error').classes('text-red-600 font-bold')
```

---

## Backgrounds and Borders

| Class             | Use                    |
| ----------------- | ---------------------- |
| `bg-white`        | White background       |
| `bg-gray-100`     | Light gray background  |
| `bg-blue-100`     | Light blue background  |
| `rounded`         | Rounded corners        |
| `rounded-lg`      | Larger rounded corners |
| `border`          | Add border             |
| `border-gray-300` | Gray border            |
| `shadow`          | Small shadow           |
| `shadow-lg`       | Larger shadow          |

```python
with ui.card().classes('bg-white rounded-lg shadow p-4'):
    ui.label('Card content')
```

---

## Responsive Classes

Use responsive prefixes like `sm:`, `md:`, `lg:`, and `xl:`.

| Class                        | Use                                          |
| ---------------------------- | -------------------------------------------- |
| `w-full md:w-1/2`            | Full width on mobile, half on medium screens |
| `grid-cols-1 md:grid-cols-2` | 1 column mobile, 2 columns desktop           |
| `text-sm md:text-lg`         | Bigger text on larger screens                |
| `hidden md:block`            | Hide on mobile, show on desktop              |
| `block md:hidden`            | Show on mobile, hide on desktop              |

```python
with ui.grid(columns=1).classes('w-full md:grid-cols-2 gap-4'):
    ui.card().classes('p-4')
    ui.card().classes('p-4')
```

---

## Styles

Use `.style()` when you need exact CSS.

```python
ui.label('Custom').style('color: purple; font-size: 22px;')
```

| Style      | Example                                |
| ---------- | -------------------------------------- |
| Width      | `.style('width: 320px;')`              |
| Height     | `.style('height: 200px;')`             |
| Color      | `.style('color: red;')`                |
| Background | `.style('background-color: #f3f4f6;')` |
| Border     | `.style('border: 1px solid #ccc;')`    |
| Overflow   | `.style('overflow: auto;')`            |

```python
with ui.element().style('height: 300px; overflow-y: auto;'):
    ui.label('Scrollable content')
```

---

## Props

Use `.props()` for Quasar-specific component options.

```python
ui.button('Save').props('color=primary rounded unelevated')
```

Common props:

| Prop             | Use                  |
| ---------------- | -------------------- |
| `color=primary`  | Primary theme color  |
| `color=negative` | Error/danger color   |
| `color=positive` | Success color        |
| `flat`           | Flat button style    |
| `outline`        | Outlined button      |
| `rounded`        | Rounded component    |
| `dense`          | Compact component    |
| `filled`         | Filled input style   |
| `outlined`       | Outlined input style |
| `clearable`      | Add clear button     |
| `readonly`       | Read-only input      |
| `disable`        | Disabled component   |

```python
ui.input('Search').props('outlined dense clearable')
ui.button('Delete').props('color=negative outline')
```

---

## Input Styling

Some inputs are Quasar wrappers, so style the inner input using `input-class` or `input-style`.

```python
ui.input('Name').props('input-class="text-lg"')
ui.input('Amount').props('input-style="text-align: right"')
```

NiceGUI notes that inputs wrap native input elements, so direct styling may need `input-class` or `input-style`.

---

## Default Classes, Styles, and Props

Set defaults before creating elements.

```python
ui.button.default_props('rounded unelevated')
ui.card.default_classes('p-4 shadow')
ui.label.default_classes('text-gray-800')
```

Example:

```python
ui.button.default_props('color=primary rounded')
ui.button('Save')
ui.button('Cancel')
```

NiceGUI supports default props, classes, and styles for element classes; they apply to elements created after the defaults are set.

---

## Common NiceGUI Layout Recipes

### Centered Page

```python
with ui.column().classes('w-full min-h-screen items-center justify-center'):
    with ui.card().classes('w-full max-w-md p-6'):
        ui.label('Login').classes('text-2xl font-bold')
```

### Header Bar

```python
with ui.header().classes('items-center justify-between'):
    ui.label('My App').classes('text-xl font-bold')
    ui.button('Settings').props('flat')
```

### Responsive Card Grid

```python
with ui.grid(columns=1).classes('w-full grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'):
    for i in range(6):
        with ui.card().classes('p-4'):
            ui.label(f'Card {i + 1}')
```

### Full-Width Form

```python
with ui.card().classes('w-full max-w-xl p-4 gap-4'):
    ui.input('Name').classes('w-full').props('outlined')
    ui.input('Email').classes('w-full').props('outlined')
    ui.button('Submit').classes('w-full').props('color=primary')
```

### Scrollable Area

```python
with ui.element().classes('w-full').style('height: 400px; overflow-y: auto;'):
    for i in range(100):
        ui.label(f'Row {i}')
```

---

## Quick Rule

| Need                               | Use                                       |
| ---------------------------------- | ----------------------------------------- |
| Spacing, layout, color, typography | `.classes()`                              |
| Exact CSS value                    | `.style()`                                |
| Quasar widget behavior/variant     | `.props()`                                |
| Reuse global styling               | `.default_classes()` / `.default_props()` |
| Inner input styling                | `input-class` / `input-style` props       |
