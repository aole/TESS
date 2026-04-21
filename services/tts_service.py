import io
import base64
from typing import List

class TTSService:
    def __init__(self):
        self.pipeline = None
        self.loading = False
    
    def ensure_pipeline(self):
        if self.pipeline is None and not self.loading:
            self.loading = True
            try:
                # Lazy import to avoid slowing down imports
                import os
                import warnings
                os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
                warnings.filterwarnings("ignore", category=FutureWarning, module="torch.*")
                warnings.filterwarnings("ignore", category=UserWarning, module="torch.*")
                from kokoro import KPipeline
                self.pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M')
            except Exception as e:
                print(f"Failed to initialize TTS pipeline: {e}")
            finally:
                self.loading = False
                
    def warmup(self):
        self.ensure_pipeline()
        if self.pipeline:
            try:
                # Dummy generation to load the voice tensor
                list(self.pipeline("a", voice='af_heart'))
            except Exception:
                pass
                
    def generate_audio_b64(self, text: str, voice: str = 'af_heart') -> List[str]:
        if not self.pipeline:
            self.ensure_pipeline()
            
        if not self.pipeline or not text.strip():
            return []
            
        import soundfile as sf
            
        try:
            generator = self.pipeline(text, voice=voice)
            b64_audios = []
            for i, (gs, ps, audio) in enumerate(generator):
                buffer = io.BytesIO()
                # audio is a numpy array (1D float32) at 24000Hz
                sf.write(buffer, audio, 24000, format='WAV')
                b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
                b64_audios.append(b64_str)
            return b64_audios
        except Exception as e:
            print(f"TTS Generation Error: {e}")
            return []

    def generate_audio_bytes(self, text: str, voice: str = 'af_heart') -> bytes:
        if not self.pipeline:
            self.ensure_pipeline()
            
        if not self.pipeline or not text.strip():
            return b""
            
        import soundfile as sf
        import numpy as np
            
        try:
            generator = self.pipeline(text, voice=voice)
            full_audio = []
            for i, (gs, ps, audio) in enumerate(generator):
                full_audio.append(audio)
            
            if not full_audio:
                return b""
                
            combined_audio = np.concatenate(full_audio)
            
            buffer = io.BytesIO()
            sf.write(buffer, combined_audio, 24000, format='WAV')
            return buffer.getvalue()
        except Exception as e:
            print(f"TTS Error: {e}")
            return b""

    def generate_audio_full_b64(self, text: str, voice: str = 'af_heart') -> str:
        data = self.generate_audio_bytes(text, voice)
        return base64.b64encode(data).decode('utf-8') if data else ""

tts_service = TTSService()
