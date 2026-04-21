from nicegui import ui, app
from services.tts_service import tts_service, VOICES
import base64
import os
import time
import re
from datetime import datetime

AUDIO_DIR = 'data/audio'
os.makedirs(AUDIO_DIR, exist_ok=True)


def create_page():
    with ui.column().classes('w-full max-w-4xl mx-auto p-8 gap-6'):
        with ui.row().classes('items-center gap-3 mb-4'):
            ui.icon('volume_up', size='48px').classes('text-indigo-400')
            with ui.column().classes('gap-0'):
                ui.label('Audio Synthesis').classes('text-3xl font-bold text-white')
                ui.label('Generate high-quality speech from text').classes('text-slate-400')

        with ui.card().classes('w-full glass-panel p-6 border-white/10'):
            with ui.column().classes('w-full gap-4'):
                ui.label('Input Text').classes('text-sm font-medium text-slate-300 uppercase tracking-wider')
                text_input = ui.textarea(
                    placeholder='Type something here to convert to speech...',
                    value='Hello! I am your AI-powered speech synthesizer. Enter any text here and click generate to hear it spoken back to you.'
                ).classes('w-full').props('outlined rows=10 input-style="color: white; font-size: 1.1rem; line-height: 1.6;"')

                with ui.row().classes('w-full items-end gap-4'):
                    with ui.column().classes('flex-grow'):
                        ui.label('Voice Selection').classes('text-xs font-medium text-slate-400 mb-1')
                        voice_select = ui.select(options=VOICES, value='af_heart', with_input=True).classes('w-full').props('outlined dense dark')
                    
                    generate_btn = ui.button('Generate Speech', icon='record_voice_over', on_click=lambda: generate()) \
                        .classes('h-12 px-6 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98]')
                    generate_btn.props('no-caps shadow-lg')

        with ui.card().classes('w-full glass-panel p-6 border-white/10'):
            with ui.column().classes('w-full gap-4'):
                ui.label('Generated Playback').classes('text-sm font-medium text-slate-300 uppercase tracking-wider')
                player_container = ui.element('div').classes('w-full')
                with player_container:
                    audio_player = ui.audio('').classes('w-full shadow-inner rounded-lg')

        def refresh_player(filename: str):
            player_container.clear()
            with player_container:
                ui.audio(f'/data/audio/{filename}').classes('w-full shadow-inner rounded-lg').props('autoplay')

        async def generate():
            if not text_input.value.strip():
                ui.notify('Please enter some text first', type='warning', color='orange')
                return

            generate_btn.props('loading')
            try:
                ui.notify('Synthesizing speech...', type='info', color='indigo')
                from nicegui import run
                audio_bytes = await run.cpu_bound(tts_service.generate_audio_bytes, text_input.value, voice=voice_select.value)
                if audio_bytes:
                    # Generate dynamic filename
                    prefix = text_input.value[:32]
                    # Convert spaces and special characters to underscore
                    sanitized = re.sub(r'[^a-zA-Z0-9]+', '_', prefix).strip('_')
                    if not sanitized:
                        sanitized = "audio"
                    
                    # Compact date and time: YYYYMMDDHHMMSS
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    filename = f"{sanitized}-{timestamp}.wav"
                    filepath = os.path.join(AUDIO_DIR, filename)

                    with open(filepath, 'wb') as f:
                        f.write(audio_bytes)
                    
                    refresh_player(filename)
                    ui.notify('Synthesis Finished!', type='positive', color='green')
                else:
                    ui.notify('Generated audio was empty!', type='negative', color='red')
            except Exception as e:
                ui.notify(f'Error: {str(e)}', type='negative', color='red')
            finally:
                generate_btn.props(remove='loading')


