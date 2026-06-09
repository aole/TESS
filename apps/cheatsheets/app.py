from pathlib import Path

from nicegui import ui


def render():
    base_dir = Path(__file__).parent

    def discover_cheatsheets():
        return sorted(
            [path for path in base_dir.glob('*.md') if path.name.lower() != 'tutorial.md'],
            key=lambda path: path.stem.lower(),
        )

    def display_name(markdown_path: Path) -> str:
        title = markdown_path.stem.replace('_', ' ').replace('-', ' ').strip()
        return title.title()

    def load_markdown(filename: str):
        markdown_path = base_dir / filename
        try:
            return markdown_path.read_text(encoding='utf-8')
        except Exception as exc:
            return f'Could not load `{filename}`: {exc}'

    cheatsheets = discover_cheatsheets()

    if not cheatsheets:
        with ui.column().classes('w-full max-w-7xl mx-auto p-6 gap-4'):
            ui.label('Cheatsheets').classes('text-3xl font-bold text-white')
            ui.label('No markdown cheatsheets were found in this directory.').classes('text-sm text-gray-400')
        return

    state = {'active': cheatsheets[0]}

    with ui.column().classes('w-full mx-auto gap-6'):
        with ui.row().classes('w-full gap-3 items-start flex-nowrap'):
            with ui.column().classes('gap-1 min-w-[200px]'):
                @ui.refreshable
                def render_cheatsheet_list():
                    for markdown_path in cheatsheets:
                        title = display_name(markdown_path)
                        is_active = markdown_path == state['active']
                        button_classes = 'w-full justify-start text-left px-2 py-1.5 rounded-lg text-xs no-caps'
                        button_classes += ' bg-indigo-500/20 text-white' if is_active else ' text-gray-200 bg-white/5 hover:bg-white/10'
                        ui.button(
                            title,
                            on_click=lambda path=markdown_path: show_sheet(path),
                        ).props('flat dense').classes(button_classes)

                render_cheatsheet_list()

            with ui.card().classes('flex-grow min-w-[320px] p-4 bg-white/5 border border-white/10 rounded-2xl'):
                sheet_content = ui.markdown('').classes('text-gray-200 prose prose-invert max-w-none')

                def show_sheet(markdown_path: Path):
                    state['active'] = markdown_path
                    sheet_content.set_content(load_markdown(markdown_path.name))
                    render_cheatsheet_list.refresh()

                show_sheet(cheatsheets[0])
