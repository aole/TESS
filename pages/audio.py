from nicegui import ui, app
from utils.ui_components import ui_list, ui_list_item
from services.tts_service import tts_service, VOICES
from utils.ollama_client import client
import base64
import os
import time
import re
import json
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

    # --- Right Drawer: Story Processing ---
    right_drawer = ui.right_drawer(value=True).classes('bg-[#18181b] border-l border-white/10 p-4')
    
    # State for multi-speaker processing
    state = {
        'segments': [],      # List of {'speaker': ..., 'text': ...}
        'speaker_voices': {}, # Map of speaker_name -> voice_id
        'is_processing': False
    }

    with right_drawer:
        ui.label('Story Studio').classes('text-xl font-bold text-white mb-4')
        
        process_btn = ui.button('Process Text', icon='psychology', on_click=lambda: process_text()) \
            .classes('w-full mb-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg')
        process_btn.props('no-caps')

        status_label = ui.label('').classes('text-xs text-slate-500 italic mb-2')
        progress_bar = ui.linear_progress(value=0, show_value=False).classes('w-full mb-4')
        progress_bar.set_visibility(False)

        speaker_settings_container = ui.column().classes('w-full gap-4')
        
        generate_multi_btn = ui.button('Generate Full Audio', icon='auto_awesome', on_click=lambda: generate_multi()) \
            .classes('w-full mt-6 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg')
        generate_multi_btn.props('no-caps shadow-lg')
        generate_multi_btn.set_visibility(False)

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
                ).classes('w-full').props('outlined rows=15 input-style="color: white; font-size: 1.1rem; line-height: 1.6;"')

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

    async def process_text():
        if not text_input.value.strip():
            ui.notify('Please enter text to process', type='warning')
            return
        
        process_btn.props('loading')
        progress_bar.set_visibility(True)
        progress_bar.set_value(0)
        
        try:
            # Load config to get story model
            with open('config.json', 'r') as f:
                config = json.load(f)
            model = config.get('default_models', {}).get('story_processing', 'gemma4:e4b')
            
            # --- Pass 1: Speaker Identification & Metadata ---
            status_label.set_text('Pass 1: Identifying characters...')
            progress_bar.set_value(0.1)
            
            pass1_prompt = f"""Identify all characters in the following story, including a "Narrator" for descriptive parts. 
For each character, specify their gender (Male, Female, or Neutral) and a brief description of their voice personality.
Return ONLY a JSON list of objects.
Example: [{{"name": "Alice", "gender": "Female", "description": "High-pitched and curious"}}, ...]

Text:
{text_input.value}
"""
            resp1 = await client.chat(model=model, messages=[{'role': 'user', 'content': pass1_prompt}], stream=False)
            content1 = resp1.get('message', {}).get('content', '')
            match1 = re.search(r'\[\s*\{.*\}\s*\]', content1, re.DOTALL)
            speakers = json.loads(match1.group(0), strict=False) if match1 else json.loads(content1, strict=False)
            
            state['speakers'] = speakers
            unique_names = [s['name'] for s in speakers]
            
            # Update UI immediately with speaker cards
            speaker_settings_container.clear()
            with speaker_settings_container:
                ui.label('Assign Voices').classes('text-sm font-medium text-slate-400 uppercase tracking-wider mb-2')
                for s in speakers:
                    name = s['name']
                    gender = s.get('gender', 'Neutral')
                    desc = s.get('description', '')
                    
                    # PERSISTENCE: Check if we already assigned a voice to this speaker in this session
                    if name in state['speaker_voices']:
                        default_voice = state['speaker_voices'][name]
                    else:
                        # Smart voice assignment
                        is_female = 'female' in gender.lower()
                        is_male = 'male' in gender.lower()
                        
                        if 'narrator' in name.lower():
                            default_voice = 'af_heart'
                        elif is_female:
                            default_voice = 'af_bella'
                        elif is_male:
                            default_voice = 'am_adam'
                        else:
                            default_voice = 'af_sky'
                        
                        state['speaker_voices'][name] = default_voice
                    
                    with ui.card().classes('w-full p-3 bg-white/5 border border-white/10'):
                        with ui.row().classes('w-full justify-between items-start'):
                            ui.label(name).classes('text-sm font-bold text-indigo-300')
                            ui.badge(gender).classes('bg-indigo-900/50 text-[10px]')
                        
                        if desc:
                            ui.label(desc).classes('text-xs text-slate-400 italic mb-2')
                            
                        ui.select(
                            options=VOICES,
                            value=default_voice,
                            with_input=True,
                            on_change=lambda e, n=name: state['speaker_voices'].update({n: e.value})
                        ).classes('w-full').props('outlined dense dark')

            # --- Pass 2: Text Segmentation (Chunked) ---
            status_label.set_text('Pass 2: Segmenting text...')
            progress_bar.set_value(0.3)
            
            # Split text into chunks paragraph by paragraph
            def get_chunks(text):
                # Try splitting by double newlines first (standard paragraph separation)
                chunks = [p.strip() for p in text.split('\n\n') if p.strip()]
                if len(chunks) <= 1:
                    # Fallback to single newlines if no double newlines are detected
                    chunks = [p.strip() for p in text.split('\n') if p.strip()]
                return chunks

            text_chunks = get_chunks(text_input.value)
            all_segments = []
            
            for i, chunk in enumerate(text_chunks):
                chunk_prog = 0.3 + (i / len(text_chunks)) * 0.6
                progress_bar.set_value(chunk_prog)
                status_label.set_text(f'Segmenting chunk {i+1}/{len(text_chunks)}...')
                
                pass2_prompt = f"""You are a script segmenter. 
Characters: {', '.join(unique_names)}

CONTEXT (Full Story):
{text_input.value}

---
TASK: Segment the following SECTION into a JSON list of objects.

CRITICAL:
- Do NOT add, remove, or change any words. Stick strictly to the SECTION text.
- Distinguish dialogue from narrative tags.
- Example: "This is weird!" Bob said "Who did this?"
  Output: [
    {{"speaker": "Bob", "text": "This is weird!"}},
    {{"speaker": "Narrator", "text": "Bob said"}},
    {{"speaker": "Bob", "text": "Who did this?"}}
  ]

SECTION TO SEGMENT:
{chunk}
"""
                resp2 = await client.chat(model=model, messages=[{'role': 'user', 'content': pass2_prompt}], stream=False)
                content2 = resp2.get('message', {}).get('content', '')
                match2 = re.search(r'\[\s*\{.*\}\s*\]', content2, re.DOTALL)
                chunk_segments = json.loads(match2.group(0), strict=False) if match2 else json.loads(content2, strict=False)
                all_segments.extend(chunk_segments)
            
            status_label.set_text('Finishing up...')
            progress_bar.set_value(1.0)
            
            # Update the input text with annotations for user editing
            annotated_text = ""
            for seg in all_segments:
                annotated_text += f"[{seg['speaker']}] {seg['text']}\n\n"
            
            text_input.set_value(annotated_text.strip())
            state['segments'] = all_segments
            generate_multi_btn.set_visibility(True)
            ui.notify(f'Script generated with {len(all_segments)} segments', type='positive')
            
        except Exception as e:
            ui.notify(f'Processing error: {str(e)}', type='negative')
            print(f"Process text error: {e}")
        finally:
            process_btn.props(remove='loading')
            progress_bar.set_visibility(False)
            status_label.set_text('')

    async def generate_multi():
        # Parse the annotated text from the input area
        raw_text = text_input.value.strip()
        if not raw_text:
            ui.notify('No text to generate', type='warning')
            return
            
        # Regex to find [Speaker] text...
        import re
        pattern = r'\[([^\]]+)\]\s*(.*?)(?=\s*\[|$)'
        matches = re.findall(pattern, raw_text, re.DOTALL)
        
        segments = [{'speaker': m[0].strip(), 'text': m[1].strip()} for m in matches]
        
        if not segments:
            ui.notify('No valid segments found. Use [Speaker Name] format.', type='warning')
            return
            
        generate_multi_btn.props('loading')
        try:
            ui.notify('Starting synthesis...', color='indigo')
            
            import soundfile as sf
            import numpy as np
            import io
            from nicegui import run
            
            all_audio_data = []
            
            for i, seg in enumerate(segments):
                speaker = seg['speaker']
                text = seg['text']
                if not text: continue
                
                # Try to find the voice for this speaker name (case insensitive)
                voice = 'af_heart'
                for s_name, s_voice in state['speaker_voices'].items():
                    if s_name.lower() == speaker.lower():
                        voice = s_voice
                        break
                
                ui.notify(f'Segment {i+1}/{len(segments)} ({speaker})...', color='indigo', duration=1)
                
                audio_bytes = await run.cpu_bound(
                    tts_service.generate_audio_bytes,
                    text,
                    voice=voice
                )
                
                if audio_bytes:
                    buffer = io.BytesIO(audio_bytes)
                    data, samplerate = sf.read(buffer)
                    all_audio_data.append(data)
            
            if not all_audio_data:
                ui.notify('No audio was generated!', type='negative')
                return
            
            combined = np.concatenate(all_audio_data)
            
            # Use original text (or first 32 chars) for filename
            clean_prefix = re.sub(r'\[[^\]]+\]', '', raw_text[:64]).strip()
            sanitized = re.sub(r'[^a-zA-Z0-9]+', '_', clean_prefix[:32]).strip('_')
            if not sanitized: sanitized = "story"
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{sanitized}-{timestamp}.wav"
            filepath = os.path.join(AUDIO_DIR, filename)
            
            final_buffer = io.BytesIO()
            sf.write(final_buffer, combined, 24000, format='WAV')
            
            metadata = {
                'speaker': 'Annotated Story',
                'comment': f'Segments: {len(segments)}',
                'software': 'TESS Story Studio v2',
                'date': datetime.now().strftime('%Y-%m-%d'),
            }
            final_bytes = tts_service._embed_wav_metadata(final_buffer.getvalue(), metadata)
            
            with open(filepath, 'wb') as f:
                f.write(final_bytes)
                
            refresh_player(filename)
            ui.notify('Audio generated from script!', type='positive')
            
        except Exception as e:
            ui.notify(f'Generation error: {str(e)}', type='negative')
            print(f"Generate multi error: {e}")
        finally:
            generate_multi_btn.props(remove='loading')

    # Remove the old generate function or keep it as a backup?
    # The user wanted to "remove" the old stuff, so I'll just not use it.

    # Initial population of the audio list
    refresh_audio_list()
