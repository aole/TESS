import os
import asyncio
from nicegui import ui, run, app
from services.visual_service import generate_image_task


_VISUAL_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
_VISUAL_DIR  = 'data/visual'


def create_page():
    if 'visual_positive_prompt' not in app.storage.user:
        app.storage.user['visual_positive_prompt'] = (
            "masterpiece, best quality, score_7, safe, abandoned cathedral, nature reclaiming architecture, "
            "vines and flowers, shafts of sunlight, dust particles, tranquil atmosphere, Studio Ghibli inspired"
        )
    if 'visual_negative_prompt' not in app.storage.user:
        app.storage.user['visual_negative_prompt'] = (
            "worst quality, low quality, score_1, score_2, score_3, artist name, sepia"
        )
    if 'visual_image_size' not in app.storage.user:
        app.storage.user['visual_image_size'] = '1024x1024'
    if 'visual_inference_steps' not in app.storage.user:
        app.storage.user['visual_inference_steps'] = 30

    # ── Main two-column layout ───────────────────────────────────────────────
    with ui.row().classes('w-full max-w-screen-2xl mx-auto gap-6 p-4 flex-nowrap items-start'):

        # Left column – image area (70%)
        with ui.column().classes(
            'rounded-lg border border-white/10 overflow-hidden bg-black/20 '
            'items-center justify-center relative'
        ).style('flex: 7; min-height: 768px;') as image_container:
            last_image = app.storage.user.get('visual_last_image')
            if last_image and os.path.exists(last_image):
                ui.image(f'/{last_image}').classes('w-full h-full object-contain rounded-lg shadow-xl')
            else:
                ui.icon('image', size='64px').classes('text-white/10 mb-4')
                ui.label('Generated image will appear here').classes('text-white/30 text-lg')

        # Right column – settings (30%)
        with ui.column().classes('gap-6').style('flex: 3;'):
            prompt = ui.textarea(
                'Positive Prompt', placeholder='masterpiece, best quality, …'
            ).classes('w-full text-lg').props('outlined rows="10"').bind_value(
                app.storage.user, 'visual_positive_prompt'
            )

            negative_prompt = ui.textarea(
                'Negative Prompt', placeholder='worst quality, low quality, …'
            ).classes('w-full').props('outlined rows="4"').bind_value(
                app.storage.user, 'visual_negative_prompt'
            )

            with ui.column().classes('w-full gap-1'):
                ui.label('Image Size').classes('text-sm text-gray-400')
                image_size = ui.select(
                    options={
                        '1024x1024': '1024 × 1024 (1:1)',
                        '896x1152':  '896 × 1152 (3:4)',
                        '1152x896':  '1152 × 896 (4:3)',
                    }
                ).classes('w-full').bind_value(app.storage.user, 'visual_image_size')

            with ui.column().classes('w-full gap-1'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label('Inference Steps').classes('text-sm text-gray-400')
                    steps_label = ui.label(
                        str(app.storage.user['visual_inference_steps'])
                    ).classes('text-sm text-gray-300 font-mono')
                steps = ui.slider(
                    min=1, max=50,
                    on_change=lambda e: steps_label.set_text(str(int(e.value)))
                ).classes('w-full').bind_value(app.storage.user, 'visual_inference_steps')

            # Generate / Clear
            with ui.row().classes('w-full gap-4 mt-2 flex-nowrap'):
                generate_btn = ui.button('Generate', icon='brush').classes(
                    'flex-grow h-16 text-xl '
                    'bg-gradient-to-r from-purple-500 to-indigo-500 '
                    'hover:from-purple-600 hover:to-indigo-600 shadow-lg'
                )
                clear_btn = ui.button(icon='delete').classes(
                    'w-16 h-16 bg-red-500/20 text-red-400 hover:bg-red-500/40 shadow-lg'
                ).tooltip('Clear Image')

            # Visual History Grid button
            history_btn = ui.button('Visual History Grid', icon='photo_library').classes(
                'w-full h-12 bg-white/5 hover:bg-white/10 '
                'text-white/70 border border-white/10 shadow'
            )

    # ── Helper: restore the "no image" placeholder ───────────────────────────
    def show_placeholder():
        image_container.clear()
        with image_container:
            ui.icon('image', size='64px').classes('text-white/10 mb-4')
            ui.label('Generated image will appear here').classes('text-white/30 text-lg')

    # ── Helper: show a single image full-size inside image_container ─────────
    def show_image(path: str):
        """path is the web-accessible URL string (e.g. '/data/visual/foo.png')."""
        image_container.clear()
        with image_container:
            ui.image(path).classes('w-full h-full object-contain rounded-lg shadow-xl')

    # ── Helper: open the history grid inside image_container ─────────────────
    def show_history():
        image_container.clear()
        with image_container:
            # Header bar
            with ui.row().classes('w-full items-center justify-between px-4 pt-3 pb-1').style(
                'flex-shrink: 0;'
            ):
                ui.label('Generation History').classes(
                    'text-white/60 text-sm font-semibold uppercase tracking-widest'
                )
                ui.button(icon='close', on_click=_restore_last).props('flat dense').classes(
                    'text-white/40 hover:text-white/80'
                ).tooltip('Back to current image')

            if not os.path.isdir(_VISUAL_DIR):
                ui.label('No images found.').classes('text-white/30 m-auto')
                return

            images = sorted(
                [f for f in os.listdir(_VISUAL_DIR)
                 if os.path.splitext(f)[1].lower() in _VISUAL_EXTS],
                reverse=True,
            )

            if not images:
                ui.label('No images yet.').classes('text-white/30 m-auto')
                return

            # Scrollable grid
            with ui.element('div').style(
                'width: 100%;'
                'overflow-y: auto;'
                'flex: 1;'
                'padding: 8px 12px 12px;'
            ):
                with ui.element('div').style(
                    'display: grid;'
                    'grid-template-columns: repeat(5, 1fr);'
                    'gap: 8px;'
                ):
                    for fname in images:
                        src = f'/{_VISUAL_DIR}/{fname}'
                        with ui.element('div').style(
                            'position: relative; overflow: hidden; border-radius: 6px;'
                            'border: 1px solid rgba(255,255,255,0.08); cursor: pointer;'
                            'aspect-ratio: 1 / 1; background: rgba(0,0,0,0.3);'
                            'transition: transform 0.15s ease, box-shadow 0.15s ease;'
                        ).on('click', lambda s=src: show_image(s)):
                            ui.image(src).style(
                                'width:100%; height:100%; object-fit:cover; display:block;'
                            )
                            with ui.element('div').style(
                                'position:absolute; bottom:0; left:0; right:0;'
                                'background: linear-gradient(transparent, rgba(0,0,0,0.75));'
                                'padding: 4px 6px; font-size: 9px;'
                                'color: rgba(255,255,255,0.45);'
                                'white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'
                            ):
                                ui.label(fname)

    def _restore_last():
        """Go back to the last generated image (or placeholder)."""
        last = app.storage.user.get('visual_last_image')
        if last and os.path.exists(last):
            show_image(f'/{last}')
        else:
            show_placeholder()

    history_btn.on('click', show_history)

    # ── Generate handler ─────────────────────────────────────────────────────
    async def on_generate():
        if not prompt.value:
            ui.notify('Please enter a positive prompt', type='warning')
            return

        generate_btn.disable()
        ui.notify('Generating image… This may take a minute or two.', type='info', timeout=5000)
        image_container.clear()

        with image_container:
            with ui.column().classes('items-center justify-center gap-4 w-full px-12'):
                ui.icon('auto_awesome', size='48px').classes('text-purple-400/60 mb-2')
                progress_label = ui.label('Preparing…').classes(
                    'text-white/50 text-sm font-mono tracking-widest'
                )
                progress_bar = ui.linear_progress(
                    value=0, size='12px', show_value=False
                ).classes('w-full').props('rounded color=purple')
                ui.label('Generating image — this may take a moment').classes(
                    'text-white/20 text-xs mt-1'
                )

        loop = asyncio.get_event_loop()

        def on_progress(step: int, total: int):
            if total == 0:
                return
            fraction = min(step / total, 1.0)
            label_text = f'Step {step} / {total}'

            def _update():
                try:
                    progress_bar.set_value(fraction)
                    progress_label.set_text(label_text)
                except Exception:
                    pass

            loop.call_soon_threadsafe(_update)

        try:
            w_str, h_str = image_size.value.split('x')
            output_path = await run.io_bound(
                generate_image_task,
                prompt.value, negative_prompt.value,
                int(steps.value), int(w_str), int(h_str),
                on_progress,
            )
            app.storage.user['visual_last_image'] = output_path
            image_container.clear()
            with image_container:
                ui.image(f'/{output_path}').classes(
                    'w-full h-full object-contain rounded-lg shadow-xl'
                )
            ui.notify('Image generated successfully!', type='positive')

        except Exception as e:
            import traceback
            traceback.print_exc()
            image_container.clear()
            with image_container:
                ui.label(f'Error: {str(e)}').classes('text-red-400')
            ui.notify(f'Failed to generate image: {str(e)}', type='negative')
        finally:
            generate_btn.enable()

    def on_clear():
        app.storage.user['visual_last_image'] = None
        show_placeholder()

    generate_btn.on('click', on_generate)
    clear_btn.on('click', on_clear)
