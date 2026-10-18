import threading
import time
import uuid
from itertools import chain

from voice_assistant.config import AUDIO_DIR
from voice_assistant.llm.ollama_client import OllamaClient
from voice_assistant.stt.transcriber import Transcriber
from voice_assistant.tts.synthesizer import Synthesizer
from voice_assistant.utils.text import SentenceSplitter

REPLY_DIR = AUDIO_DIR / "replies"
FALLBACK_REPLY = "Sorry, I could not understand that. Could you say it again?"


class VoicePipeline:
    def __init__(self):
        REPLY_DIR.mkdir(parents=True, exist_ok=True)
        self.transcriber = Transcriber()
        self.llm = OllamaClient()
        self.synthesizer = Synthesizer()
        self.lock = threading.Lock()
        self._warmup_llm()

    def _warmup_llm(self):
        print(f"Warming up Ollama model '{self.llm.model}'...")
        try:
            seconds = self.llm.warmup()
            print(f"Ollama model warm in {seconds}s")
        except RuntimeError as error:
            print(
                f"WARNING: Ollama warm-up fail aachu ({error}). "
                "Server start aagum, aana first request slow-a irukkum."
            )

    def transcribe(self, audio_path, language=None):
        with self.lock:
            return self.transcriber.transcribe(audio_path, language=language)

    def chat(self, text):
        with self.lock:
            reply = self.llm.chat(text)
            return {"reply": reply, "stats": dict(self.llm.last_stats)}

    def reset(self):
        with self.lock:
            self.llm.reset()

    def speak(self, text):
        filename = f"reply_{uuid.uuid4().hex[:8]}.wav"
        with self.lock:
            result = self.synthesizer.synthesize_to_file(text, filename=f"replies/{filename}")
        result["filename"] = filename
        return result

    def voice(self, audio_path, language=None):
        total_start = time.perf_counter()

        stt = self.transcribe(audio_path, language=language)
        user_text = stt["text"]

        if not user_text:
            reply_text = FALLBACK_REPLY
            llm_stats = {"first_token_latency": 0.0, "total_time": 0.0}
        else:
            chat = self.chat(user_text)
            reply_text = chat["reply"] or FALLBACK_REPLY
            llm_stats = chat["stats"]

        tts = self.speak(reply_text)

        return {
            "user_text": user_text,
            "detected_language": stt["language"],
            "reply_text": reply_text,
            "audio_file": tts["filename"],
            "timings": {
                "stt": stt["processing_time"],
                "llm_first_token": llm_stats.get("first_token_latency", 0.0),
                "llm_total": llm_stats.get("total_time", 0.0),
                "tts": tts["processing_time"],
                "total": round(time.perf_counter() - total_start, 2),
            },
        }

    def new_session(self):
        return OllamaClient()

    def _sentence_event(self, sentence, index):
        with self.lock:
            result = self.synthesizer.synthesize_to_bytes(sentence)
        return {
            "type": "sentence",
            "index": index,
            "text": sentence,
            "audio": result["audio_bytes"],
            "audio_duration": result["audio_duration"],
            "tts_time": result["processing_time"],
        }

    def _done_event(self, reply, stt_time, stats, tts_total, first_audio, turn_start):
        return {
            "type": "done",
            "reply": reply,
            "timings": {
                "stt": stt_time,
                "llm_first_token": stats.get("first_token_latency", 0.0),
                "llm_total": stats.get("total_time", 0.0),
                "tts": round(tts_total, 2),
                "first_audio": first_audio,
                "total": round(time.perf_counter() - turn_start, 2),
            },
        }

    def stream_turn(self, session, audio_path=None, text=None, language=None):
        turn_start = time.perf_counter()
        stt_time = 0.0

        if audio_path is not None:
            stt = self.transcribe(audio_path, language=language)
            text = stt["text"]
            stt_time = stt["processing_time"]
            yield {"type": "transcript", "text": text, "language": stt["language"]}

        tts_total = 0.0
        first_audio = None
        index = 0

        if not text:
            event = self._sentence_event(FALLBACK_REPLY, index)
            tts_total = event["tts_time"]
            first_audio = round(time.perf_counter() - turn_start, 2)
            yield event
            yield self._done_event(FALLBACK_REPLY, stt_time, {}, tts_total, first_audio, turn_start)
            return

        splitter = SentenceSplitter()
        reply_parts = []

        for token in chain(session.chat_stream(text), [None]):
            if token is None:
                sentences = splitter.flush()
            else:
                reply_parts.append(token)
                yield {"type": "token", "text": token}
                sentences = splitter.feed(token)

            for sentence in sentences:
                event = self._sentence_event(sentence, index)
                index += 1
                tts_total += event["tts_time"]
                if first_audio is None:
                    first_audio = round(time.perf_counter() - turn_start, 2)
                yield event

        reply = "".join(reply_parts).strip()
        yield self._done_event(reply, stt_time, session.last_stats, tts_total, first_audio, turn_start)