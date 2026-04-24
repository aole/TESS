from nicegui import ui, app
from utils.ui_components import ui_list, ui_list_item
from services.tts_service import tts_service
from utils.ollama_client import client
import os
import re
import struct
import json
import wave
from datetime import datetime

import soundfile as sf
import numpy as np
import io
from nicegui import run
import torch
from omnivoice import OmniVoice

omnivoice_model = None

def get_omnivoice_model():
    global omnivoice_model
    if omnivoice_model is None:
        omnivoice_model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map="cuda:0",
            dtype=torch.float16
        )
    return omnivoice_model

def generate_omnivoice(target_text, ref_audio, ref_txt):
    model = get_omnivoice_model()
    audio = model.generate(
        text=target_text,
        ref_audio=ref_audio,
        ref_text=ref_txt
    )
    return audio[0]


AUDIO_DIR = 'data/audio'
os.makedirs(AUDIO_DIR, exist_ok=True)


def get_wav_duration(filepath: str) -> str:
    """Return a human-readable duration string for a WAV file."""
    with wave.open(filepath, 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        seconds = frames / rate
    m, s = divmod(int(seconds), 60)
    return f'{m}:{s:02d}'


def get_wav_speaker(filepath: str) -> str:
    """Extract the IART (speaker) field from a WAV RIFF LIST/INFO chunk."""
    with open(filepath, 'rb') as f:
        header = f.read(12)
        if len(header) < 12 or not header.startswith(b'RIFF'):
            return ''
        
        file_size = os.path.getsize(filepath)
        
        while f.tell() + 8 <= file_size:
            chunk_header = f.read(8)
            if len(chunk_header) < 8:
                break
            chunk_id, chunk_size = struct.unpack('<4sI', chunk_header)
            
            if chunk_id == b'LIST':
                list_type = f.read(4)
                if list_type == b'INFO':
                    end_pos = f.tell() - 4 + chunk_size
                    while f.tell() + 8 <= end_pos:
                        sub_header = f.read(8)
                        if len(sub_header) < 8:
                            break
                        sub_id, sub_size = struct.unpack('<4sI', sub_header)
                        if sub_id == b'IART':
                            raw = f.read(sub_size)
                            return raw.rstrip(b'\x00').decode('utf-8', errors='replace')
                        f.seek(sub_size + (sub_size % 2), os.SEEK_CUR)
                    break
                else:
                    f.seek(chunk_size - 4 + (chunk_size % 2), os.SEEK_CUR)
            else:
                f.seek(chunk_size + (chunk_size % 2), os.SEEK_CUR)
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
        'speaker_voices': {'Narrator': 'af_heart'}, # Map of speaker_name -> voice_id
        'speaker_samples': {}, # Map of speaker_name -> sample_filename
        'speakers': [{'name': 'Narrator', 'gender': 'Male', 'description': 'male, middle-aged, moderate pitch, american accent'}],
        'is_processing': False,
        'cancel_processing': False
    }

    with right_drawer:
        ui.label('Story Studio').classes('text-xl font-bold text-white mb-4')
        
        async def toggle_process():
            if state['is_processing']:
                state['cancel_processing'] = True
                status_label.set_text('Canceling...')
                process_btn.props('loading')
            else:
                await process_text()

        process_btn = ui.button('Process Text', icon='psychology', on_click=toggle_process) \
            .classes('w-full mb-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors')
        process_btn.props('no-caps')

        status_label = ui.label('').classes('text-xs text-slate-500 italic mb-2')
        progress_bar = ui.linear_progress(value=0, show_value=False).classes('w-full mb-4')
        progress_bar.set_visibility(False)

        speaker_settings_container = ui.column().classes('w-full gap-4')
        
        generate_multi_btn = ui.button('Generate Full Audio', icon='auto_awesome', on_click=lambda: generate_multi()) \
            .classes('w-full mt-6 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg')
        generate_multi_btn.props('no-caps shadow-lg')
        generate_multi_btn.set_visibility(False)

        gen_status_label = ui.label('').classes('text-xs text-slate-500 italic mt-2 mb-2')
        gen_status_label.set_visibility(False)
        gen_progress_bar = ui.linear_progress(value=0, show_value=False).classes('w-full mb-4')
        gen_progress_bar.set_visibility(False)

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

    def render_speakers_ui():
        speaker_settings_container.clear()
        
        voice_files = []
        try:
            if os.path.exists('data/voices'):
                voice_files = sorted([f for f in os.listdir('data/voices') if f.lower().endswith('.wav')])
        except Exception:
            pass

        with speaker_settings_container:
            ui.label('Assign Voices').classes('text-sm font-medium text-slate-400 uppercase tracking-wider mb-2')
            for s in state['speakers']:
                name = s.get('name', 'Unknown')
                gender = s.get('gender', 'Neutral')
                desc = s.get('description', '')
                
                if name in state['speaker_voices']:
                    default_voice = state['speaker_voices'][name]
                else:
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
                
                if name in state['speaker_samples']:
                    default_sample = state['speaker_samples'][name]
                else:
                    default_sample = voice_files[0] if voice_files else None
                    if default_sample:
                        state['speaker_samples'][name] = default_sample
                
                with ui.card().classes('w-full p-3 bg-white/5 border border-white/10'):
                    with ui.row().classes('w-full justify-between items-start'):
                        ui.label(name).classes('text-sm font-bold text-indigo-300')
                        ui.badge(gender).classes('bg-indigo-900/50 text-[10px]')
                    
                    if desc:
                        ui.label(desc).classes('text-xs text-slate-400 italic mb-2')
                        
                    with ui.row().classes('w-full items-center gap-2 flex-nowrap'):
                        voice_sample_select = ui.select(
                            options=voice_files,
                            value=default_sample,
                            label='Voice Sample',
                            with_input=True,
                            on_change=lambda e, n=name: state['speaker_samples'].update({n: e.value})
                        ).classes('flex-grow w-0').props('outlined dense dark')
                        
                        sample_player = ui.audio('').classes('hidden')
                        
                        play_btn = ui.button(icon='play_arrow').classes('bg-indigo-600 hover:bg-indigo-700 text-white shrink-0').props('round dense flat')
                        
                        class PlayState:
                            playing = False
                            
                        def setup_player(btn, player, sel):
                            st = PlayState()
                            
                            def toggle(e):
                                if st.playing:
                                    player.pause()
                                    btn.props('icon=play_arrow')
                                    st.playing = False
                                else:
                                    if sel.value:
                                        player.set_source(f'/data/voices/{sel.value}')
                                        player.play()
                                        btn.props('icon=stop')
                                        st.playing = True
                                        
                            def reset(e):
                                btn.props('icon=play_arrow')
                                st.playing = False
                                
                            btn.on_click(toggle)
                            player.on('ended', reset)
                            
                        setup_player(play_btn, sample_player, voice_sample_select)

    async def process_text():
        if not text_input.value.strip():
            ui.notify('Please enter text to process', type='warning')
            return
        
        # Keep only Narrator before processing
        state['speakers'] = [{'name': 'Narrator', 'gender': 'Male', 'description': 'male, middle-aged, moderate pitch, american accent'}]
        state['speaker_voices'] = {k: v for k, v in state['speaker_voices'].items() if k.lower() == 'narrator'}
        render_speakers_ui()
        
        state['is_processing'] = True
        state['cancel_processing'] = False
        process_btn.set_text('Cancel Processing')
        process_btn.props('icon=cancel')
        process_btn.classes(remove='bg-indigo-600 hover:bg-indigo-700', add='bg-red-600 hover:bg-red-700')
        
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
            
            pass1_system = """You are an expert casting director and script analyzer. Your task is to identify all unique characters in the provided story.
You must always include a "Narrator" character for descriptive, non-dialogue parts of the text.
Analyze the text to determine the gender (Male, Female, or Neutral) and a brief voice personality for each character.
The description for each character MUST strictly follow this exact structure: <gender>, <age>, <pitch>, <accent>.
Only the following values can be used for the description field:
- gender: male | female
- age: child | teenager | young adult | middle-aged | elderly
- pitch: very low pitch | low pitch | moderate pitch | high pitch | very high pitch
- accent: american accent | british accent | australian accent | canadian accent | indian accent | chinese accent | korean accent | japanese accent | portuguese accent | russian accent
Output MUST be exclusively a valid JSON list of objects with keys: 'name', 'gender', 'description'. Do not include any conversational text or markdown formatting."""

            pass1_user = f"Text to analyze:\n{text_input.value}"

            resp1 = await client.chat(model=model, messages=[
                {'role': 'system', 'content': pass1_system},
                {'role': 'user', 'content': pass1_user}
            ], stream=False)
            content1 = resp1.get('message', {}).get('content', '')
            
            def extract_json_list(text):
                start = text.find('[')
                end = text.rfind(']')
                if start != -1 and end != -1 and start < end:
                    try:
                        return json.loads(text[start:end+1], strict=False)
                    except Exception:
                        pass
                try:
                    return json.loads(text, strict=False)
                except Exception:
                    return []

            speakers = extract_json_list(content1)
            if not any(s.get('name', '').lower() == 'narrator' for s in speakers if isinstance(s, dict)):
                speakers.insert(0, {'name': 'Narrator', 'gender': 'Male', 'description': 'male, middle-aged, moderate pitch, american accent'})
            
            state['speakers'] = speakers
            unique_names = [s.get('name', 'Unknown') for s in speakers if isinstance(s, dict)]
            
            # Update UI immediately with speaker cards
            render_speakers_ui()

            # --- Pass 2: Static Pass & Speaker Assignment ---
            status_label.set_text('Pass 2: Segmenting text and identifying speakers...')
            progress_bar.set_value(0.3)
            
            def split_dialogue_and_narrative(text):
                import re
                pattern = r'("[^"]*"|“[^”]*”|‘.+?’(?!\w)|(?<!\w)\'.+?\'(?!\w))'
                parts = re.split(pattern, text, flags=re.DOTALL)
                
                segments = []
                for p in parts:
                    p = p.strip()
                    if not p:
                        continue
                    if (p.startswith('"') and p.endswith('"')) or \
                       (p.startswith('“') and p.endswith('”')) or \
                       (p.startswith('‘') and p.endswith('’')) or \
                       (p.startswith("'") and p.endswith("'")):
                        segments.append({"type": "dialogue", "text": p})
                    else:
                        segments.append({"type": "narrator", "text": p})
                return segments

            static_segments = split_dialogue_and_narrative(text_input.value)
            
            all_segments = []
            dialogue_indices = []
            
            for i, seg in enumerate(static_segments):
                if seg['type'] == 'narrator':
                    all_segments.append({'speaker': 'Narrator', 'text': seg['text']})
                else:
                    all_segments.append({'speaker': 'Unknown', 'text': seg['text']})
                    dialogue_indices.append(i)
                    
            batch_size = 5
            for i in range(0, len(dialogue_indices), batch_size):
                if state['cancel_processing']:
                    ui.notify('Processing canceled', type='warning')
                    break
                    
                batch_indices = dialogue_indices[i:i+batch_size]
                
                chunk_prog = 0.3 + (i / max(1, len(dialogue_indices))) * 0.6
                progress_bar.set_value(chunk_prog)
                status_label.set_text(f'Identifying speakers for lines {i+1} to {min(i+batch_size, len(dialogue_indices))} of {len(dialogue_indices)}...')
                
                lines_to_identify = "\n".join([f"{idx+1}. {all_segments[b_idx]['text']}" for idx, b_idx in enumerate(batch_indices)])
                
                dialogue_characters = [n for n in unique_names if n.lower() != 'narrator']
                pass2_system = f"""You are a professional script analyzer. 
Your task is to identify the speaker for each of the provided dialogue lines based on the story context.
Available Characters: {', '.join(dialogue_characters)}.

CRITICAL RULES:
1. Output MUST be exclusively a valid JSON list of objects.
2. Each object must have exactly two keys: "sentence" (integer) and "speaker" (string).
3. The "sentence" number must match the numbered prefix of the provided dialogue line.
4. Assign the correct speaker from the Available Characters list. If a speaker is unknown or not in the list, use 'Unknown'.

Example Output:
[
  {{"sentence": 1, "speaker": "Alice"}},
  {{"sentence": 2, "speaker": "Bob"}}
]"""

                pass2_user = f"STORY CONTEXT:\n{text_input.value}\n\n---\nDIALOGUE LINES TO IDENTIFY:\n{lines_to_identify}"

                resp2 = await client.chat(
                    model=model, 
                    messages=[
                        {'role': 'system', 'content': pass2_system},
                        {'role': 'user', 'content': pass2_user}
                    ], 
                    stream=False,
                    keep_alive=0 if i + batch_size >= len(dialogue_indices) else None
                )
                content2 = resp2.get('message', {}).get('content', '')
                identified_segments = extract_json_list(content2)
                
                if identified_segments and isinstance(identified_segments, list):
                    for id_seg in identified_segments:
                        try:
                            # Sentence is 1-indexed in the prompt
                            sentence_idx = int(id_seg.get('sentence', 0)) - 1
                            speaker = id_seg.get('speaker', 'Unknown')
                            
                            if 0 <= sentence_idx < len(batch_indices):
                                actual_index = batch_indices[sentence_idx]
                                all_segments[actual_index]['speaker'] = speaker
                        except (ValueError, TypeError):
                            continue
            
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
            state['is_processing'] = False
            state['cancel_processing'] = False
            process_btn.set_text('Process Text')
            process_btn.props('icon=psychology')
            process_btn.classes(remove='bg-red-600 hover:bg-red-700', add='bg-indigo-600 hover:bg-indigo-700')
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
        gen_status_label.set_visibility(True)
        gen_progress_bar.set_visibility(True)
        gen_progress_bar.set_value(0)
        
        try:
            ui.notify('Starting synthesis...', color='indigo')
            
            all_audio_data = []
            
            for i, seg in enumerate(segments):
                gen_status_label.set_text(f'Generating segment {i+1}/{len(segments)} ({seg["speaker"]})...')
                gen_progress_bar.set_value(i / max(1, len(segments)))
                
                speaker = seg['speaker']
                text = seg['text']
                if not text: continue
                
                # Try to find the voice sample for this speaker name (case insensitive)
                voice_sample = state['speaker_samples'].get(speaker)
                if not voice_sample:
                    for s_name, s_sample in state['speaker_samples'].items():
                        if s_name.lower() == speaker.lower():
                            voice_sample = s_sample
                            break
                            
                if not voice_sample:
                    voice_sample = list(state['speaker_samples'].values())[0] if state['speaker_samples'] else None
                    
                if not voice_sample:
                    ui.notify(f"No voice sample selected for {speaker}", type="warning")
                    continue
                
                ui.notify(f'Segment {i+1}/{len(segments)} ({speaker})...', color='indigo', duration=1)
                
                ref_text_path = os.path.join('data/voices', voice_sample.replace('.wav', '.txt'))
                if not os.path.exists(ref_text_path):
                    ui.notify(f"Reference text not found: {ref_text_path}", type="negative")
                    continue
                    
                with open(ref_text_path, 'r', encoding='utf-8') as f:
                    ref_text = f.read().strip()
                
                ref_audio_path = os.path.join('data/voices', voice_sample)
                
                audio_data = await run.cpu_bound(
                    generate_omnivoice,
                    text,
                    ref_audio_path,
                    ref_text
                )
                
                if audio_data is not None:
                    all_audio_data.append(audio_data)
            
            if not all_audio_data:
                ui.notify('No audio was generated!', type='negative')
                return
            
            gen_status_label.set_text('Merging audio segments...')
            gen_progress_bar.set_value(1.0)
            
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
            final_bytes = tts_service.embed_wav_metadata(final_buffer.getvalue(), metadata)
            
            with open(filepath, 'wb') as f:
                f.write(final_bytes)
                
            refresh_player(filename)
            ui.notify('Audio generated from script!', type='positive')
            
        except Exception as e:
            ui.notify(f'Generation error: {str(e)}', type='negative')
            print(f"Generate multi error: {e}")
        finally:
            generate_multi_btn.props(remove='loading')
            gen_status_label.set_visibility(False)
            gen_progress_bar.set_visibility(False)
            gen_status_label.set_text('')

    # Remove the old generate function or keep it as a backup?
    # The user wanted to "remove" the old stuff, so I'll just not use it.

    # Initial population of the audio list
    refresh_audio_list()
    
    # Initialize UI
    render_speakers_ui()
