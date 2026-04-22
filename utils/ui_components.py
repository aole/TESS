"""
utils/ui_components.py
────────────────────────────────────────────────────────────────────────────
Standardized UI component library for the Ollama Model Manager.

Components
----------
ui_card        – settings / content card with optional heading & footer;
                 supports collapsible heading (collapsible=True, collapsed=False)
ui_info_card   – compact display-only info panel (e.g. system info);
                 also supports collapsible=True / collapsed=True
ui_list        – scrollable sidebar list container with an optional header
ui_list_item   – clickable row inside a ui_list with title, subtitle,
                 active-state highlight, and an optional action button

Quick reference
---------------

    from utils.ui_components import ui_card, ui_info_card, ui_list, ui_list_item

    # ── Cards ────────────────────────────────────────────────────────────────
    # Standard (non-collapsible) card
    with ui_card(heading="Logging", heading_icon="article", heading_color="indigo",
                 footer_text="> Saved to logs/", footer_markdown=True):
        ui.checkbox("Enable logging")

    # Collapsible card (starts expanded by default)
    with ui_card(heading="Advanced", heading_icon="tune", collapsible=True):
        ui.checkbox("Debug mode")

    # Collapsible card that starts collapsed
    with ui_card(heading="Danger Zone", collapsible=True, collapsed=True):
        ui.button("Reset all settings")

    with ui_info_card(heading="System", heading_color="indigo"):
        ui.label("OS: Windows 11")

    # ── Lists ────────────────────────────────────────────────────────────────
    with ui_list(heading="History", heading_icon="history",
                 action_icon="add", on_action=lambda: new_chat()):
        pass   # populated dynamically

    # Inside a refresh function, inside the list container:
    with ui_list_item(
        title="My Chat",
        subtitle="2026-04-21",
        active=True,
        on_click=lambda: load_chat(),
        action_icon="delete",
        action_color="red-4",
        on_action=lambda: delete_chat(),
    ):
        pass   # optional extra body content
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Optional

from nicegui import ui


# ══════════════════════════════════════════════════════════════════════════════
# ui_card
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def ui_card(
    *,
    # ── Heading ──────────────────────────────────────────────────────────────
    heading: Optional[str] = None,
    heading_icon: Optional[str] = None,
    heading_color: str = "indigo",
    # ── Collapsible ──────────────────────────────────────────────────────────
    collapsible: bool = True,
    collapsed: bool = False,
    # ── Card-level styling ───────────────────────────────────────────────────
    extra_classes: str = "",
    # ── Footer ───────────────────────────────────────────────────────────────
    footer: Optional[Callable[[], None]] = None,
    footer_text: Optional[str] = None,
    footer_markdown: bool = False,
):
    """
    Context-manager that yields a NiceGUI card with:
    • optional heading row  (icon + label)
    • body slot  ← everything inside the ``with`` block goes here
    • optional footer  (callable *or* plain / markdown text)

    When ``collapsible=True`` the heading row becomes a clickable toggle
    that shows / hides the body and footer.  A rotating chevron icon
    indicates the current state.  ``collapsed=True`` starts the card closed.

    Parameters
    ----------
    heading         : Card title shown at the top.
    heading_icon    : Material-icon name placed left of the title (optional).
    heading_color   : Tailwind colour prefix for icon/title accent (default "indigo").
    collapsible     : If True, the heading row toggles body visibility (default True).
    collapsed       : Initial collapsed state (only relevant when collapsible=True).
    extra_classes   : Additional Tailwind classes appended to the card.
    footer          : Zero-argument callable that builds the footer UI.
    footer_text     : Static text rendered as the footer.
    footer_markdown : If True, ``footer_text`` is rendered as Markdown.
    """
    base_classes = (
        "w-full p-6 bg-black/20 border border-white/5 rounded-xl " + extra_classes
    ).strip()

    with ui.card().classes(base_classes):
        # ── Heading ──────────────────────────────────────────────────────────
        if heading:
            header_row_classes = "items-center gap-2 mb-4"
            if collapsible:
                header_row_classes += " cursor-pointer select-none w-full justify-between"

            with ui.row().classes(header_row_classes) as header_row:
                with ui.row().classes("items-center gap-2"):
                    if heading_icon:
                        ui.icon(heading_icon, size="20px").classes(
                            f"text-{heading_color}-400"
                        )
                    ui.label(heading).classes(
                        f"text-xl font-bold text-{heading_color}-400"
                    )

                if collapsible:
                    chevron = ui.icon(
                        "expand_less" if not collapsed else "expand_more",
                        size="20px",
                    ).classes(f"text-{heading_color}-400 transition-transform duration-200")

        # ── Body + Footer (wrapped so they can be toggled together) ───────────
        with ui.column().classes("w-full gap-0") as body_col:
            if collapsible and collapsed:
                body_col.set_visibility(False)

            # ── Body slot ────────────────────────────────────────────────────
            yield

            # ── Footer ───────────────────────────────────────────────────────
            if footer is not None:
                ui.separator().classes("my-4 bg-white/10")
                footer()
            elif footer_text:
                ui.separator().classes("my-4 bg-white/10")
                if footer_markdown:
                    ui.markdown(footer_text).classes("text-sm text-gray-500 italic")
                else:
                    ui.label(footer_text).classes("text-sm text-gray-500 italic")

        # ── Wire up toggle logic ──────────────────────────────────────────────
        if collapsible and heading:
            _state = {"collapsed": collapsed}

            def _toggle(state=_state, col=body_col, chev=chevron):
                state["collapsed"] = not state["collapsed"]
                col.set_visibility(not state["collapsed"])
                chev.props(f'name={"expand_more" if state["collapsed"] else "expand_less"}')

            header_row.on("click", lambda _: _toggle())


# ══════════════════════════════════════════════════════════════════════════════
# ui_info_card
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def ui_info_card(
    *,
    heading: Optional[str] = None,
    heading_color: str = "indigo",
    extra_classes: str = "",
    # ── Collapsible ──────────────────────────────────────────────────────────
    collapsible: bool = True,
    collapsed: bool = False,
):
    """
    Lighter-weight variant used for display-only info panels (e.g. system
    info) with a smaller, all-caps heading and a more translucent background.

    When ``collapsible=True`` the heading acts as a clickable toggle that
    shows / hides the card body.  ``collapsed=True`` starts the card closed.

    Parameters
    ----------
    heading       : Section label (rendered uppercase, small, accented).
    heading_color : Tailwind colour prefix for the heading label.
    extra_classes : Additional Tailwind classes appended to the card.
    collapsible   : If True, the heading row toggles body visibility (default True).
    collapsed     : Initial collapsed state (only relevant when collapsible=True).
    """
    base_classes = (
        "w-full p-4 bg-black/30 border border-white/5 rounded-xl " + extra_classes
    ).strip()

    with ui.card().classes(base_classes):
        if heading:
            heading_row_classes = (
                "flex items-center justify-between w-full mb-3"
                + (" cursor-pointer select-none" if collapsible else "")
            )
            with ui.row().classes(heading_row_classes) as heading_row:
                ui.label(heading).classes(
                    f"text-xs font-bold text-{heading_color}-400 "
                    "uppercase tracking-widest"
                )
                if collapsible:
                    chevron = ui.icon(
                        "expand_less" if not collapsed else "expand_more",
                        size="16px",
                    ).classes(f"text-{heading_color}-400 transition-transform duration-200")

        with ui.column().classes("w-full gap-0") as body_col:
            if collapsible and collapsed:
                body_col.set_visibility(False)

            yield

        if collapsible and heading:
            _state = {"collapsed": collapsed}

            def _toggle(state=_state, col=body_col, chev=chevron):
                state["collapsed"] = not state["collapsed"]
                col.set_visibility(not state["collapsed"])
                chev.props(f'name={"expand_more" if state["collapsed"] else "expand_less"}')

            heading_row.on("click", lambda _: _toggle())


# ══════════════════════════════════════════════════════════════════════════════
# ui_list
# ══════════════════════════════════════════════════════════════════════════════

def ui_list(
    *,
    heading: Optional[str] = None,
    heading_icon: Optional[str] = None,
    action_icon: Optional[str] = None,
    action_tooltip: Optional[str] = None,
    on_action: Optional[Callable[[], None]] = None,
    container_classes: str = "",
) -> ui.column:
    """
    Returns a ``ui.column`` that acts as a scrollable sidebar list.

    A sticky header row is rendered above the scrollable body when
    ``heading`` is supplied. An optional icon-button (e.g. "add") can be
    placed at the right of the header via ``action_icon`` / ``on_action``.

    Parameters
    ----------
    heading           : Label shown in the header row (optional).
    heading_icon      : Material-icon name shown left of the heading label.
    action_icon       : Material-icon name for the header action button.
    action_tooltip    : Tooltip text for the action button.
    on_action         : Callback fired when the action button is clicked.
    container_classes : Extra Tailwind classes on the scrollable body column.

    Returns
    -------
    ui.column
        The scrollable body container — use ``with`` or ``.clear()`` /
        ``with container:`` inside your refresh functions.

    Example
    -------
        list_body = ui_list(
            heading="History",
            heading_icon="history",
            action_icon="add",
            action_tooltip="New Chat",
            on_action=lambda: new_chat(),
        )
        with list_body:
            ui.label("item")
    """
    # Outer column owns the full panel height
    with ui.column().classes("w-full h-full p-0 m-0 no-wrap gap-0"):

        # ── Header ───────────────────────────────────────────────────────────
        if heading or action_icon:
            with ui.row().classes(
                "w-full items-center justify-between p-4 "
                "border-b border-white/5 shrink-0"
            ):
                with ui.row().classes("items-center gap-2"):
                    if heading_icon:
                        ui.icon(heading_icon, size="20px").classes("text-indigo-400")
                    if heading:
                        ui.label(heading).classes("text-lg font-bold text-gray-200")

                if action_icon and on_action:
                    btn = ui.button(
                        icon=action_icon, on_click=on_action
                    ).props("flat round dense color=primary")
                    if action_tooltip:
                        btn.tooltip(action_tooltip)

        # ── Scrollable body ───────────────────────────────────────────────────
        body_classes = (
            "w-full flex-grow overflow-y-auto p-2 gap-1 " + container_classes
        ).strip()
        body = ui.column().classes(body_classes)

    return body


# ══════════════════════════════════════════════════════════════════════════════
# ui_list_item
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def ui_list_item(
    *,
    title: str,
    subtitle: Optional[str] = None,
    subtitle_icon: Optional[str] = None,
    active: bool = False,
    on_click: Optional[Callable[[], None]] = None,
    # ── Optional trailing action button ─────────────────────────────────────
    action_icon: Optional[str] = None,
    action_color: str = "red-4",
    action_tooltip: Optional[str] = None,
    on_action: Optional[Callable[[], None]] = None,
    extra_classes: str = "",
):
    """
    Context-manager that renders a single clickable list row inside a
    ``ui_list`` body (or any column).

    Layout
    ------
    ┌──────────────────────────────────────────────────┬───────┐
    │  [subtitle_icon]  title                          │  [×]  │
    │                   subtitle                       │       │
    │  ← body slot (optional extra content) ─────────  │       │
    └──────────────────────────────────────────────────┴───────┘

    The action button (×) is hidden by default and revealed on hover via
    Tailwind ``group-hover:opacity-100``.

    Parameters
    ----------
    title           : Primary text (truncated if too long).
    subtitle        : Secondary line shown in gray below the title.
    subtitle_icon   : Small Material icon shown before the subtitle.
    active          : Whether this item is the currently selected one.
    on_click        : Callback fired when the row is clicked.
    action_icon     : Material icon for the trailing action button (e.g. "delete").
    action_color    : Quasar/Tailwind colour for the action button (default "red-4").
    action_tooltip  : Tooltip for the action button.
    on_action       : Callback fired when the action button is clicked.
                      Uses ``click.stop`` to avoid triggering ``on_click``.
    extra_classes   : Additional Tailwind classes on the root card.
    """
    active_cls = (
        "bg-white/10 border-indigo-400/30" if active
        else "hover:bg-white/5 border-white/5"
    )
    base_classes = (
        f"w-full py-1 px-3 text-sm cursor-pointer transition-colors "
        f"{active_cls} relative group border {extra_classes}"
    ).strip()

    click_handler = on_click or (lambda: None)

    with ui.card().classes(base_classes).on("click", lambda _: click_handler()):
        # ── Text column ───────────────────────────────────────────────────────
        with ui.column().classes("w-full min-w-0 gap-0"):
            ui.label(title).classes(
                "font-medium text-gray-200 truncate w-full pr-6"
            )
            if subtitle:
                with ui.row().classes("items-center gap-1"):
                    if subtitle_icon:
                        ui.icon(subtitle_icon, size="14px").classes("text-gray-500")
                    ui.label(subtitle).classes("text-xs text-gray-500 truncate")

        # ── Optional body slot ────────────────────────────────────────────────
        yield

        # ── Trailing action button ────────────────────────────────────────────
        if action_icon and on_action:
            btn = (
                ui.button(icon=action_icon)
                .on("click.stop", lambda _: on_action())
                .props(f"flat round dense size=sm color={action_color}")
                .classes(
                    "absolute right-1 top-1/2 -translate-y-1/2 "
                    "opacity-0 group-hover:opacity-100 transition-opacity bg-black/60"
                )
            )
            if action_tooltip:
                btn.tooltip(action_tooltip)
