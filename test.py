from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.play import play
import os

load_dotenv()

elevenlabs = ElevenLabs(
  api_key="sk_843947f289161919edf551084805d5830f98dd8c40b55d38",
)

audio = elevenlabs.text_to_speech.convert(
    text="Dạ Doctor Check xin nghe ạ!",
    voice_id="hpp4J3VqNfWAUOO0d1Us",  # "George" - browse voices at elevenlabs.io/app/voice-library
    model_id="eleven_v3",
    language_code="vi",
    output_format="mp3_44100_128",
)

play(audio)


