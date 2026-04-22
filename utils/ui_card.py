"""
utils/ui_card.py
────────────────────────────────────────────────────────────────────────────
Standardized card component for the Ollama Model Manager.

Usage
-----
    from utils.ui_card import ui_card

    # Minimal – just a body
    with ui_card():
        ui.label("Hello from the body")

    # With a heading only
    with ui_card(heading="Logging Configuration"):
        ui.checkbox("Enable Chat Logging")

    # With a heading and an icon
    with ui_card(heading="Graphics", heading_icon="videocam", heading_color="purple"):
        ui.label("GPU info here")

    # With a heading AND a footer
    with ui_card(
        heading="Note Categories",
        footer_text="> Logs are saved to `logs/llm_debug.log`",
        footer_markdown=True,
    ):
        ui.checkbox("Enable logging")

    # Provide your own footer slot via footer callable
    def my_footer():
        ui.button("Save", icon="save")

    with ui_card(heading="Custom Footer", footer=my_footer):
        ui.label("body content")
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Optional

from nicegui import ui


@contextmanager
def ui_card(
    *,
    # ── Heading ─────────────────────────────────────────────────────────────
    heading: Optional[str] = None,
    heading_icon: Optional[str] = None,
    heading_color: str = "indigo",
    # ── Card-level styling ──────────────────────────────────────────────────
    extra_classes: str = "",
    # ── Footer ──────────────────────────────────────────────────────────────
    footer: Optional[Callable[[], None]] = None,
    footer_text: Optional[str] = None,
    footer_markdown: bool = False,
):
    """
    Context-manager that yields a NiceGUI card with:
    • optional heading row (icon + label)
    • body slot  ← everything inside the ``with`` block goes here
    • optional footer (callable *or* plain/markdown text)

    Parameters
    ----------
    heading         : Card title shown at the top.
    heading_icon    : Material-icon name placed left of the title (optional).
    heading_color   : Tailwind colour prefix for icon/title accent  (default "indigo").
    extra_classes   : Additional Tailwind classes appended to the card.
    footer          : Zero-argument callable that builds the footer UI.
    footer_text     : Static text rendered as the footer.
    footer_markdown : If True, ``footer_text`` is rendered as Markdown.
    """
    base_classes = (
        "w-full p-6 bg-black/20 border border-white/5 rounded-xl "
        + extra_classes
    ).strip()

    with ui.card().classes(base_classes):
        # ── Heading ──────────────────────────────────────────────────────────
        if heading:
            with ui.row().classes("items-center gap-2 mb-4"):
                if heading_icon:
                    ui.icon(heading_icon, size="20px").classes(
                        f"text-{heading_color}-400"
                    )
                ui.label(heading).classes(
                    f"text-xl font-bold text-{heading_color}-400"
                )

        # ── Body ─────────────────────────────────────────────────────────────
        yield

        # ── Footer ───────────────────────────────────────────────────────────
        if footer is not None:
            ui.separator().classes("my-4 bg-white/10")
            footer()
        elif footer_text:
            ui.separator().classes("my-4 bg-white/10")
            if footer_markdown:
                ui.markdown(footer_text).classes(
                    "text-sm text-gray-500 italic"
                )
            else:
                ui.label(footer_text).classes("text-sm text-gray-500 italic")


@contextmanager
def ui_info_card(
    *,
    heading: Optional[str] = None,
    heading_color: str = "indigo",
    extra_classes: str = "",
):
    """
    Lighter-weight variant used for display-only info panels (e.g. system
    info) with a smaller, all-caps heading and a more translucent background.

    Parameters
    ----------
    heading       : Section label (rendered uppercase, small, accented).
    heading_color : Tailwind colour prefix for the heading label.
    extra_classes : Additional Tailwind classes appended to the card.
    """
    base_classes = (
        "w-full p-4 bg-black/30 border border-white/5 rounded-xl "
        + extra_classes
    ).strip()

    with ui.card().classes(base_classes):
        if heading:
            ui.label(heading).classes(
                f"text-xs font-bold text-{heading_color}-400 "
                "uppercase tracking-widest mb-3"
            )
        yield
