import io
import base64
from typing import List, Dict

VOICES = {
    # American English
    'af_alloy': 'American Female - Alloy',
    'af_aoede': 'American Female - Aoede',
    'af_bella': 'American Female - Bella',
    'af_heart': 'American Female - Heart',
    'af_jessica': 'American Female - Jessica',
    'af_kore': 'American Female - Kore',
    'af_nicole': 'American Female - Nicole',
    'af_nova': 'American Female - Nova',
    'af_river': 'American Female - River',
    'af_sarah': 'American Female - Sarah',
    'af_sky': 'American Female - Sky',
    'am_adam': 'American Male - Adam',
    'am_echo': 'American Male - Echo',
    'am_eric': 'American Male - Eric',
    'am_fenrir': 'American Male - Fenrir',
    'am_liam': 'American Male - Liam',
    'am_michael': 'American Male - Michael',
    'am_onyx': 'American Male - Onyx',
    'am_puck': 'American Male - Puck',
    'am_santa': 'American Male - Santa',
    # British English
    'bf_alice': 'British Female - Alice',
    'bf_emma': 'British Female - Emma',
    'bf_isabella': 'British Female - Isabella',
    'bf_lily': 'British Female - Lily',
    'bm_daniel': 'British Male - Daniel',
    'bm_fable': 'British Male - Fable',
    'bm_george': 'British Male - George',
    'bm_lewis': 'British Male - Lewis',
    # Spanish
    'ef_dora': 'Spanish Female - Dora',
    'em_alex': 'Spanish Male - Alex',
    'em_santa': 'Spanish Male - Santa',
    # French
    'ff_siwis': 'French Female - Siwis',
    # Hindi
    'hf_alpha': 'Hindi Female - Alpha',
    'hf_beta': 'Hindi Female - Beta',
    'hm_omega': 'Hindi Male - Omega',
    'hm_psi': 'Hindi Male - Psi',
    # Italian
    'if_sara': 'Italian Female - Sara',
    'im_nicola': 'Italian Male - Nicola',
    # Japanese voices require pyopenjtalk (no Windows binary wheel; needs C++ build tools)
    # Uncomment below only after successfully installing pyopenjtalk:
    # 'jf_alpha': 'Japanese Female - Alpha',
    # 'jf_gongitsune': 'Japanese Female - Gongitsune',
    # 'jf_nezumi': 'Japanese Female - Nezumi',
    # 'jf_tebukuro': 'Japanese Female - Tebukuro',
    # 'jm_kumo': 'Japanese Male - Kumo',
    # Portuguese
    'pf_dora': 'Portuguese Female - Dora',
    'pm_alex': 'Portuguese Male - Alex',
    'pm_santa': 'Portuguese Male - Santa',
    # Chinese
    'zf_xiaobei': 'Chinese Female - Xiaobei',
    'zf_xiaoni': 'Chinese Female - Xiaoni',
    'zf_xiaoxiao': 'Chinese Female - Xiaoxiao',
    'zf_xiaoyi': 'Chinese Female - Xiaoyi',
    'zm_yunjian': 'Chinese Male - Yunjian',
    'zm_yunxi': 'Chinese Male - Yunxi',
    'zm_yunxia': 'Chinese Male - Yunxia',
    'zm_yunyang': 'Chinese Male - Yunyang',
}

class TTSService:
    def __init__(self):
        self.pipelines = {}   # Cache pipelines by lang_code
        self.failed = set()   # Track lang_codes that failed so we don't retry
        self.loading = False
    
    def ensure_pipeline(self, lang_code='a'):
        if lang_code in self.failed:
            return None
        if lang_code not in self.pipelines and not self.loading:
            self.loading = True
            try:
                # Lazy import to avoid slowing down imports
                import os
                import warnings
                os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
                warnings.filterwarnings("ignore", category=FutureWarning, module="torch.*")
                warnings.filterwarnings("ignore", category=UserWarning, module="torch.*")
                from kokoro import KPipeline
                self.pipelines[lang_code] = KPipeline(lang_code=lang_code, repo_id='hexgrad/Kokoro-82M')
            except Exception as e:
                print(f"Failed to initialize TTS pipeline for '{lang_code}': {e}")
                self.failed.add(lang_code)  # Don't retry this lang_code
            finally:
                self.loading = False
        return self.pipelines.get(lang_code)

    def get_lang_code(self, voice: str) -> str:
        if not voice:
            return 'a'
        # The first character of the voice name corresponds to the lang_code
        # af_ -> a, bf_ -> b, jf_ -> j, etc.
        return voice[0].lower()
                
    def warmup(self):
        lang_code = 'a'
        pipeline = self.ensure_pipeline(lang_code)
        if pipeline:
            try:
                # Dummy generation to load the voice tensor
                list(pipeline("a", voice='af_heart'))
            except Exception:
                pass
                
    def generate_audio_b64(self, text: str, voice: str = 'af_heart') -> List[str]:
        lang_code = self.get_lang_code(voice)
        pipeline = self.ensure_pipeline(lang_code)
            
        if not pipeline or not text.strip():
            return []
            
        import soundfile as sf
            
        try:
            generator = pipeline(text, voice=voice)
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
        lang_code = self.get_lang_code(voice)
        pipeline = self.ensure_pipeline(lang_code)
            
        if not pipeline or not text.strip():
            return b""
            
        import soundfile as sf
        import numpy as np
            
        try:
            generator = pipeline(text, voice=voice)
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
