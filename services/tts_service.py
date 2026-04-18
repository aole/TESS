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
                os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
                from kokoro import KPipeline
                self.pipeline = KPipeline(lang_code='a')
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

tts_service = TTSService()
