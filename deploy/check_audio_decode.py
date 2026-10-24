import wave

from faster_whisper import decode_audio

with wave.open("/tmp/silence.wav", "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(16000)
    audio.writeframes(bytes(32000))

sample_count = len(decode_audio("/tmp/silence.wav"))
if sample_count != 16000:
    raise SystemExit(f"decoded {sample_count} samples from one second of audio, expected 16000")
