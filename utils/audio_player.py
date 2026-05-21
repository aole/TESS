from nicegui import ui, app
from utils.config import config_manager
import asyncio
import re
from services.tts_service import tts_service

class AudioPlayer:
    """
    Manages Text-to-Speech playback and audio state.
    Handles both manual playback of existing messages and automatic playback during streaming.
    """
    def __init__(self, page_client, on_state_change=None):
        self.page_client = page_client
        self.on_state_change = on_state_change
        self.playing_tts_id = None
        self.tts_cursors = {}
        self.tts_generation_complete = False
        self._lock = asyncio.Lock()
        
        # Regex for sentence boundary to avoid splitting on common abbreviations
        self.boundary_pattern = (
            r'(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bProf)'
            r'(?<!\bSr)(?<!\bJr)(?<!\bSt)(?<!\bCapt)(?<!\bCol)'
            r'(?<!\bGen)(?<!\bLt)(?<!\bSgt)(?<!\b[A-Za-z])'
            r'([.!?\n]+)(\s*)'
        )

    async def _inject_js(self):
        """Injects the JavaScript audio queue management logic if not already present."""
        await ui.run_javascript("""
            if (!window.audioQueue) {
                window.audioQueue = [];
                window.isPlayingAudio = false;
                window.currentAudioObj = null;
                
                window.stopAudio = function() {
                    window.audioQueue = [];
                    if (window.currentAudioObj) {
                        window.currentAudioObj.pause();
                        window.currentAudioObj = null;
                    }
                    window.isPlayingAudio = false;
                };
                
                window.playNextAudio = function() {
                    if (window.audioQueue.length > 0 && !window.isPlayingAudio) {
                        window.isPlayingAudio = true;
                        let src = window.audioQueue.shift();
                        window.currentAudioObj = new Audio('data:audio/wav;base64,' + src);
                        window.currentAudioObj.onended = function() {
                            window.isPlayingAudio = false;
                            window.playNextAudio();
                        };
                        window.currentAudioObj.play().catch(e => {
                            console.error("Audio play error", e);
                            window.isPlayingAudio = false;
                            window.playNextAudio();
                        });
                    }
                };
            }
        """)

    async def play_audio_js(self, b64_str):
        """Pushes a base64 audio chunk to the JavaScript queue."""
        if self.page_client._deleted:
            return
        await self._inject_js()
        await ui.run_javascript(f"window.audioQueue.push('{b64_str}'); window.playNextAudio();")

    async def stop(self):
        """Stops all playback and resets state."""
        async with self._lock:
            if not self.page_client._deleted:
                with self.page_client:
                    await ui.run_javascript("if(window.stopAudio) window.stopAudio();")
            self.playing_tts_id = None
            self.tts_generation_complete = False
            if self.on_state_change and not self.page_client._deleted:
                self.on_state_change()

    async def play_message(self, msg):
        """Plays the full content of a message."""
        if self.playing_tts_id == msg['id']:
            await self.stop()
            return

        await self.stop()
        self.playing_tts_id = msg['id']
        self.tts_generation_complete = False
        if self.on_state_change:
            self.on_state_change()

        content = msg.get('content', '')
        # Split into sentences while keeping delimiters and spaces
        parts = re.split(self.boundary_pattern, content, flags=re.IGNORECASE)
        sentences = []
        current_s = ""
        # re.split with capturing groups returns (text, delim, space, text, delim, space...)
        for i in range(0, len(parts), 3):
            current_s += parts[i]
            if i + 1 < len(parts): current_s += parts[i+1] # delimiter
            if i + 2 < len(parts): current_s += parts[i+2] # whitespace
            
            if current_s.strip():
                sentences.append(current_s)
                current_s = ""
        if current_s.strip():
            sentences.append(current_s)
            
        for s in sentences:
            if self.playing_tts_id != msg['id']:
                break
            await self._play_tts_chunk(s, msg['id'])
            
        if self.playing_tts_id == msg['id']:
            self.tts_generation_complete = True

    async def _play_tts_chunk(self, text_chunk, msg_id):
        """Internal helper to generate and play a single text chunk."""
        if self.playing_tts_id != msg_id:
            return
        
        try:
            voice = config_manager.get_tts_voice()
            b64_list = await asyncio.to_thread(tts_service.generate_audio_b64, text_chunk, voice=voice)
            if self.playing_tts_id != msg_id:
                return
            for b64 in b64_list:
                if self.page_client._deleted:
                    return
                with self.page_client:
                    await self.play_audio_js(b64)
        except Exception as e:
            print(f"TTS Error: {e}")

    async def sync_tts_state(self):
        """Checks if JS playback has finished and updates state accordingly."""
        if self.playing_tts_id and self.tts_generation_complete:
            if self.page_client._deleted:
                return
            with self.page_client:
                try:
                    is_playing = await ui.run_javascript('return !!(window.isPlayingAudio || (window.audioQueue && window.audioQueue.length > 0));')
                    if not is_playing:
                        self.playing_tts_id = None
                        self.tts_generation_complete = False
                        if self.on_state_change and not self.page_client._deleted:
                            self.on_state_change()
                except Exception:
                    pass

    async def process_stream_chunk(self, msg_id, content, is_done=False):
        """Handles streaming text by chunking it into sentences for real-time TTS."""
        if not config_manager.is_tts_enabled():
            return

        if msg_id not in self.tts_cursors:
            self.tts_cursors[msg_id] = 0
            if self.playing_tts_id != msg_id:
                await self.stop()
                self.playing_tts_id = msg_id
                self.tts_generation_complete = False
                if self.on_state_change:
                    self.on_state_change()

        spoken = self.tts_cursors[msg_id]
        unspoken = content[spoken:]
        
        if is_done:
            if unspoken.strip():
                self.tts_cursors[msg_id] += len(unspoken)
                asyncio.create_task(self._play_tts_chunk(unspoken, msg_id))
            if self.playing_tts_id == msg_id:
                self.tts_generation_complete = True
            return

        # Look for the first sentence boundary in the unspoken text
        matches = list(re.finditer(self.boundary_pattern, unspoken, re.IGNORECASE))
        if matches:
            flush_end_pos = matches[0].end()
            sentence = unspoken[:flush_end_pos]
            self.tts_cursors[msg_id] += flush_end_pos
            asyncio.create_task(self._play_tts_chunk(sentence, msg_id))
