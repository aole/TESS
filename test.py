import numpy as np
import soundfile as sf
from faster_qwen3_tts import FasterQwen3TTS

model = FasterQwen3TTS.from_pretrained("Qwen/Qwen3-TTS-12Hz-0.6B-Base")
ref_audio = "ref_audio.wav"
ref_text = (
    "I'm confused why some people have super short timelines, yet at the same time are bullish on scaling up "
    "reinforcement learning atop LLMs. If we're actually close to a human-like learner, then this whole approach "
    "of training on verifiable outcomes is doomed."
)

# Non-streaming — returns all audio at once
audio_list, sr = model.generate_voice_clone(
    text="Hello world!", language="English",
    ref_audio=ref_audio, ref_text=ref_text,
)

# Concatenate all chunks into one single array
full_audio = np.concatenate(audio_list)

# Save to disk
sf.write("output_full.wav", full_audio, sr)
print("Saved to output_full.wav")
