import torch
from omnivoice import OmniVoice
import soundfile as sf

model = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",
    device_map="cuda:0",
    dtype=torch.float16
)

for i in range(5):
    audio = model.generate(
        text="‘You ought to go quietly, and you ought to go soon,’ said Gandalf. Two or three weeks had passed, and still Frodo made no sign of getting ready to go.",
        instruct="male, elderly, low pitch, american accent",
        # ref_audio="ref01.wav",
        # ref_text="This is a test for voice design."
    )
    sf.write(f"out{i}.wav", audio[0], 24000)
