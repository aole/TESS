import torch
from omnivoice import OmniVoice
import soundfile as sf

model = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",
    device_map="cuda:0",
    dtype=torch.float16
)

ref = """‘You ought to go quietly, and you ought to go soon,’ said Gandalf.
Two or three weeks had passed, and [sigh] still Frodo made no sign of getting ready to go.
"""
# design
audio = model.generate(
    text=ref,
    instruct="female, young adult, moderate pitch, american accent",
    # instruct="male, elderly, low pitch, american accent",
    num_step=48,
    position_temperature=10.0,
    class_temperature=1.0,
    # ref_audio="ref01.wav",
    # ref_text="This is a test for voice design."
)
sf.write(f"out.wav", audio[0], 24000)
print(f"out.wav generated")

# clone

target="""There was a silence.
At last Frodo spoke to Pippin and Sam: ‘I ought to have guessed it from the way the gatekeeper greeted us,’ he said.
‘And the landlord seems to have heard something.
Why did he press us to join the company?
And why on earth did we behave so foolishly: we ought to have stayed quiet in here.’
"""
audio = model.generate(
    text=target,
    ref_audio="out.wav",
    ref_text=ref
)
sf.write(f"out_clone.wav", audio[0], 24000)
print(f"out_clone.wav generated")
