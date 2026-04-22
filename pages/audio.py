from nicegui import ui, app
from utils.ui_components import ui_list, ui_list_item
from services.tts_service import tts_service, VOICES
import base64
import os
import time
import re
from datetime import datetime

AUDIO_DIR = 'data/audio'
os.makedirs(AUDIO_DIR, exist_ok=True)


def get_wav_duration(filepath: str) -> str:
    """Return a human-readable duration string for a WAV file."""
    try:
        import wave
        with wave.open(filepath, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            seconds = frames / rate
        m, s = divmod(int(seconds), 60)
        return f'{m}:{s:02d}'
    except Exception:
        return ''


def get_wav_speaker(filepath: str) -> str:
    """Extract the IART (speaker) field from a WAV RIFF LIST/INFO chunk."""
    try:
        import struct
        with open(filepath, 'rb') as f:
            data = f.read()
        # Scan for LIST chunk
        pos = 12  # skip RIFF header
        while pos + 8 <= len(data):
            chunk_id = data[pos:pos+4]
            chunk_size = struct.unpack_from('<I', data, pos+4)[0]
            if chunk_id == b'LIST' and data[pos+8:pos+12] == b'INFO':
                # Walk INFO sub-chunks
                sub_pos = pos + 12
                end = pos + 8 + chunk_size
                while sub_pos + 8 <= end:
                    sub_id = data[sub_pos:sub_pos+4]
                    sub_size = struct.unpack_from('<I', data, sub_pos+4)[0]
                    if sub_id == b'IART':
                        raw = data[sub_pos+8:sub_pos+8+sub_size]
                        return raw.rstrip(b'\x00').decode('utf-8', errors='replace')
                    # sub-chunks are padded to even size
                    sub_pos += 8 + sub_size + (sub_size % 2)
            pos += 8 + chunk_size + (chunk_size % 2)
    except Exception:
        pass
    return ''


def create_page():
    # --- Left Drawer: Audio File List ---
    drawer = ui.left_drawer(value=True).classes('bg-[#18181b] border-r border-white/10')
    with drawer:
        audio_list_container = ui_list(
            heading='Audio Files',
            heading_icon='audio_file',
        )

    # Shared player container reference (will be set below)
    player_state = {'container': None}

    def load_audio_file(filename: str):
        container = player_state['container']
        if container is None:
            return
        container.clear()
        with container:
            ui.audio(f'/data/audio/{filename}').classes('w-full shadow-inner rounded-lg').props('autoplay')

    def delete_audio_file(filename: str):
        """Delete an audio file from disk and refresh the list."""
        fpath = os.path.join(AUDIO_DIR, filename)
        try:
            os.remove(fpath)
        except Exception as e:
            ui.notify(f'Could not delete file: {e}', type='negative', color='red')
            return
        ui.notify('Audio file deleted', type='positive', color='green')
        # Restore the placeholder player so the playback card stays visible
        container = player_state['container']
        if container is not None:
            container.clear()
            with container:
                ui.audio('').classes('w-full shadow-inner rounded-lg')
        refresh_audio_list()

    def refresh_audio_list(selected_filename: str = None):
        audio_list_container.clear()
        try:
            files = sorted(
                [f for f in os.listdir(AUDIO_DIR) if f.lower().endswith('.wav')],
                key=lambda f: os.path.getmtime(os.path.join(AUDIO_DIR, f)),
                reverse=True  # Newest first
            )
        except Exception:
            files = []

        with audio_list_container:
            if not files:
                ui.label('No audio files yet').classes('text-sm text-gray-500 italic p-4')
                return

            for fname in files:
                is_active = fname == selected_filename
                # Trim the timestamp suffix for display
                display_name = re.sub(r'-\d{14}\.wav$', '', fname).replace('_', ' ')
                fpath = os.path.join(AUDIO_DIR, fname)
                duration = get_wav_duration(fpath)
                speaker = get_wav_speaker(fpath)
                subtitle = ' \u00b7 '.join(filter(None, [duration, speaker]))

                with ui_list_item(
                    title=display_name,
                    subtitle=subtitle,
                    active=is_active,
                    on_click=lambda f=fname: load_audio_file(f),
                    action_icon='delete',
                    action_color='red-4',
                    action_tooltip='Delete file',
                    on_action=lambda f=fname: delete_audio_file(f),
                    extra_classes='rounded-lg',
                ):
                    pass

    # --- Main Content Area ---
    with ui.column().classes('w-full max-w-4xl mx-auto p-8 gap-6'):
        with ui.row().classes('items-center gap-3 mb-4'):
            ui.icon('volume_up', size='48px').classes('text-indigo-400')
            with ui.column().classes('gap-0'):
                ui.label('Audio Synthesis').classes('text-3xl font-bold text-white')
                ui.label('Generate high-quality speech from text').classes('text-slate-400')

        with ui.card().classes('w-full glass-panel p-6 border-white/10'):
            with ui.column().classes('w-full gap-4'):
                ui.label('Input Text').classes('text-sm font-medium text-slate-300 uppercase tracking-wider')

                # Persistence: Load last used text or use default
                default_text = 'Hello! I am your AI-powered speech synthesizer. Enter any text here and click generate to hear it spoken back to you.'
                text_input = ui.textarea(
                    placeholder='Type something here to convert to speech...',
                    value=app.storage.user.get('last_tts_text', default_text),
                    on_change=lambda e: app.storage.user.update({'last_tts_text': e.value})
                ).classes('w-full').props('outlined rows=10 input-style="color: white; font-size: 1.1rem; line-height: 1.6;"')

                with ui.row().classes('w-full items-end gap-4'):
                    with ui.column().classes('flex-grow'):
                        ui.label('Voice Selection').classes('text-xs font-medium text-slate-400 mb-1')
                        # Persistence: Load last used voice or use default
                        _default_voice = 'af_heart'
                        _stored_voice = app.storage.user.get('last_tts_voice', _default_voice)
                        if _stored_voice not in VOICES:
                            _stored_voice = _default_voice
                            app.storage.user.update({'last_tts_voice': _stored_voice})
                        voice_select = ui.select(
                            options=VOICES,
                            value=_stored_voice,
                            with_input=True,
                            on_change=lambda e: app.storage.user.update({'last_tts_voice': e.value})
                        ).classes('w-full').props('outlined dense dark')

                    generate_btn = ui.button('Generate Speech', icon='record_voice_over', on_click=lambda: generate()) \
                        .classes('h-12 px-6 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white rounded-lg transition-all transform hover:scale-[1.02] active:scale-[0.98]')
                    generate_btn.props('no-caps shadow-lg')

        with ui.card().classes('w-full glass-panel p-6 border-white/10'):
            with ui.column().classes('w-full gap-4'):
                ui.label('Generated Playback').classes('text-sm font-medium text-slate-300 uppercase tracking-wider')
                player_container = ui.element('div').classes('w-full')
                player_state['container'] = player_container
                with player_container:
                    ui.audio('').classes('w-full shadow-inner rounded-lg')

    def refresh_player(filename: str):
        player_state['container'].clear()
        with player_state['container']:
            ui.audio(f'/data/audio/{filename}').classes('w-full shadow-inner rounded-lg').props('autoplay')
        refresh_audio_list(selected_filename=filename)

    async def generate():
        if not text_input.value.strip():
            ui.notify('Please enter some text first', type='warning', color='orange')
            return

        generate_btn.props('loading')
        try:
            ui.notify('Synthesizing speech...', type='info', color='indigo')
            from nicegui import run
            wav_metadata = {
                    'speaker': f'{voice_select.value}/Kokoro TTS',
                    'comment': VOICES.get(voice_select.value, voice_select.value),
                    'software': 'TESS',
                    'date': datetime.now().strftime('%Y-%m-%d'),
                }
            audio_bytes = await run.cpu_bound(
                    tts_service.generate_audio_bytes,
                    text_input.value,
                    voice=voice_select.value,
                    metadata=wav_metadata,
                )
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

    # Initial population of the audio list
    refresh_audio_list()
