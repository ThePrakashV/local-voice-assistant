import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "2048"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "6"))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

PIPER_VOICE = os.getenv("PIPER_VOICE", "en_US-lessac-medium")

VAD_SILENCE_SECONDS = float(os.getenv("VAD_SILENCE_SECONDS", "1.0"))
VAD_MAX_SECONDS = float(os.getenv("VAD_MAX_SECONDS", "15"))
VAD_START_TIMEOUT = float(os.getenv("VAD_START_TIMEOUT", "8"))
VAD_MULTIPLIER = float(os.getenv("VAD_MULTIPLIER", "3.0"))
VAD_MIN_THRESHOLD = float(os.getenv("VAD_MIN_THRESHOLD", "0.01"))

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

SAMPLE_RATE = 16000
AUDIO_DIR = ROOT_DIR / "data" / "audio"
VOICES_DIR = ROOT_DIR / "models" / "voices"