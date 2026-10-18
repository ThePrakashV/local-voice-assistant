import io
import time
import wave

import sounddevice as sd
import soundfile as sf
from piper import PiperVoice

from voice_assistant.config import AUDIO_DIR, PIPER_VOICE, VOICES_DIR


class Synthesizer:
    def __init__(self, voice_name=PIPER_VOICE):
        model_path = VOICES_DIR / f"{voice_name}.onnx"
        if not model_path.exists():
            raise FileNotFoundError(
                f"Voice file illa: {model_path}. "
                f"Mudhal la 'python -m voice_assistant.tts.download_voice {voice_name}' run pannu."
            )

        print(f"Loading Piper voice '{voice_name}'...")
        start = time.perf_counter()
        self.voice = PiperVoice.load(str(model_path))
        self.load_time = round(time.perf_counter() - start, 2)
        self.voice_name = voice_name
        print(f"Voice loaded in {self.load_time}s")

    def synthesize_to_file(self, text, filename="tts_output.wav"):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        output_path = AUDIO_DIR / filename

        start = time.perf_counter()
        with wave.open(str(output_path), "wb") as wav_file:
            self.voice.synthesize_wav(text, wav_file)
        processing_time = time.perf_counter() - start

        audio_duration = sf.info(str(output_path)).duration
        rtf = processing_time / audio_duration if audio_duration > 0 else 0.0

        return {
            "path": output_path,
            "audio_duration": round(audio_duration, 2),
            "processing_time": round(processing_time, 2),
            "rtf": round(rtf, 2),
        }

    def synthesize_to_bytes(self, text):
        buffer = io.BytesIO()

        start = time.perf_counter()
        with wave.open(buffer, "wb") as wav_file:
            self.voice.synthesize_wav(text, wav_file)
        processing_time = time.perf_counter() - start

        audio_bytes = buffer.getvalue()
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            audio_duration = wav_file.getnframes() / wav_file.getframerate()

        return {
            "audio_bytes": audio_bytes,
            "audio_duration": round(audio_duration, 2),
            "processing_time": round(processing_time, 2),
        }

    def play(self, wav_path, device=None):
        data, sample_rate = sf.read(str(wav_path), dtype="float32")
        sd.play(data, sample_rate, device=device)
        sd.wait()