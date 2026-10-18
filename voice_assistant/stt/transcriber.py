import time

from faster_whisper import WhisperModel

from voice_assistant.config import (
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)


class Transcriber:
    def __init__(
        self,
        model_size=WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    ):
        print(f"Loading Whisper model '{model_size}' ({device}, {compute_type})...")
        start = time.perf_counter()
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.load_time = round(time.perf_counter() - start, 2)
        print(f"Model loaded in {self.load_time}s")

    def transcribe(self, audio_path, language=None):
        start = time.perf_counter()
        segments, info = self.model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        processing_time = round(time.perf_counter() - start, 2)

        return {
            "text": text,
            "language": info.language,
            "language_probability": round(info.language_probability, 2),
            "audio_duration": round(info.duration, 2),
            "processing_time": processing_time,
        }