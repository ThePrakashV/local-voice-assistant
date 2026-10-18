import numpy as np
import sounddevice as sd
import soundfile as sf

from voice_assistant.config import AUDIO_DIR, SAMPLE_RATE


def list_input_devices():
    hostapis = sd.query_hostapis()
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            api_name = hostapis[device["hostapi"]]["name"]
            sample_rate = int(device["default_samplerate"])
            print(f"[{index}] {device['name']} | {api_name} | default_sr={sample_rate}")


def record(seconds=5, device=None, filename="recording.wav"):
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    output_path = AUDIO_DIR / filename

    print(f"Recording {seconds} seconds... pesu!")
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    print("Recording mudinjuchu.")

    peak = float(np.max(np.abs(audio)))
    sf.write(str(output_path), audio, SAMPLE_RATE)
    return output_path, peak