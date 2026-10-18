import importlib
import os
import shutil
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

PACKAGES = [
    "fastapi",
    "uvicorn",
    "websockets",
    "dotenv",
    "pydantic",
    "numpy",
    "requests",
    "httpx",
    "sounddevice",
    "soundfile",
    "faster_whisper",
    "plotly",
    "pandas",
]


def check_python():
    print(f"[Python] {sys.version.split()[0]}")


def check_packages():
    print("\n[Packages]")
    for name in PACKAGES:
        try:
            importlib.import_module(name)
            print(f"  OK       {name}")
        except Exception as e:
            print(f"  MISSING  {name} -> {e}")


def check_ffmpeg():
    print("\n[ffmpeg]")
    path = shutil.which("ffmpeg")
    if path:
        print(f"  OK  {path}")
    else:
        print("  MISSING  ffmpeg PATH la illa")


def check_ollama():
    print("\n[Ollama]")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        models = [m["name"] for m in response.json().get("models", [])]
        print(f"  OK  Running. Models: {models}")
    except Exception as e:
        print(f"  NOT REACHABLE  {e}")


def check_audio_devices():
    print("\n[Audio Devices]")
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        for index, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                print(f"  Mic [{index}] {device['name']}")
    except Exception as e:
        print(f"  ERROR  {e}")


if __name__ == "__main__":
    check_python()
    check_packages()
    check_ffmpeg()
    check_ollama()
    check_audio_devices()