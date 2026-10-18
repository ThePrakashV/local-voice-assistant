import collections
import queue
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from voice_assistant.config import (
    AUDIO_DIR,
    SAMPLE_RATE,
    VAD_MAX_SECONDS,
    VAD_MIN_THRESHOLD,
    VAD_MULTIPLIER,
    VAD_SILENCE_SECONDS,
    VAD_START_TIMEOUT,
)

BLOCK_MS = 30
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_MS / 1000)
CALIBRATION_BLOCKS = 17
PRE_ROLL_BLOCKS = 10
START_BLOCKS = 3
TAIL_BLOCKS = 10


def block_rms(block):
    return float(np.sqrt(np.mean(np.square(block))))


def record_until_silence(
    device=None,
    silence_seconds=None,
    max_seconds=None,
    start_timeout=None,
    multiplier=None,
    min_threshold=None,
    filename="vad_input.wav",
    verbose=True,
):
    silence_seconds = VAD_SILENCE_SECONDS if silence_seconds is None else silence_seconds
    max_seconds = VAD_MAX_SECONDS if max_seconds is None else max_seconds
    start_timeout = VAD_START_TIMEOUT if start_timeout is None else start_timeout
    multiplier = VAD_MULTIPLIER if multiplier is None else multiplier
    min_threshold = VAD_MIN_THRESHOLD if min_threshold is None else min_threshold

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    output_path = AUDIO_DIR / filename
    silence_limit = max(1, int(silence_seconds * 1000 / BLOCK_MS))

    audio_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_queue.put(indata[:, 0].copy())

    def next_block():
        try:
            return audio_queue.get(timeout=2.0)
        except queue.Empty:
            return None

    pre_roll = collections.deque(maxlen=PRE_ROLL_BLOCKS)
    recorded = []
    speech_started = False
    speech_run = 0
    silent_blocks = 0
    noise = 0.0
    threshold = 0.0
    status = "max_length"

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SIZE,
        device=device,
        callback=callback,
    ):
        if verbose:
            print("Background noise calibrate pannren... amaidhiya iru (0.5s)")

        noise_levels = []
        while len(noise_levels) < CALIBRATION_BLOCKS:
            block = next_block()
            if block is None:
                break
            noise_levels.append(block_rms(block))

        if len(noise_levels) < CALIBRATION_BLOCKS:
            status = "no_audio"
        else:
            noise = float(np.median(noise_levels))
            threshold = max(noise * multiplier, min_threshold)
            if verbose:
                print(f"Noise={noise:.4f} | threshold={threshold:.4f}")
                print("Pesu... (nee amaidhi aanadhum auto-stop aagum)")

            start = time.perf_counter()
            while True:
                block = next_block()
                if block is None:
                    status = "no_audio"
                    break

                elapsed = time.perf_counter() - start
                is_speech = block_rms(block) > threshold

                if not speech_started:
                    pre_roll.append(block)
                    speech_run = speech_run + 1 if is_speech else 0
                    if speech_run >= START_BLOCKS:
                        speech_started = True
                        recorded = list(pre_roll)
                        silent_blocks = 0
                    elif elapsed > start_timeout:
                        status = "no_speech"
                        break
                else:
                    recorded.append(block)
                    if is_speech:
                        silent_blocks = 0
                    else:
                        silent_blocks += 1
                        if silent_blocks >= silence_limit:
                            status = "silence"
                            break
                    if elapsed > max_seconds:
                        status = "max_length"
                        break

    if status == "silence":
        extra = silent_blocks - TAIL_BLOCKS
        if extra > 0:
            recorded = recorded[:-extra]

    if not recorded:
        return {
            "path": None,
            "status": status,
            "duration": 0.0,
            "peak": 0.0,
            "noise": round(noise, 4),
            "threshold": round(threshold, 4),
        }

    audio = np.concatenate(recorded)
    sf.write(str(output_path), audio, SAMPLE_RATE)

    return {
        "path": output_path,
        "status": status,
        "duration": round(len(audio) / SAMPLE_RATE, 2),
        "peak": round(float(np.max(np.abs(audio))), 3),
        "noise": round(noise, 4),
        "threshold": round(threshold, 4),
    }