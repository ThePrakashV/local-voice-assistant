import argparse
import queue
import time

import numpy as np
import sounddevice as sd

from voice_assistant.config import SAMPLE_RATE

BLOCK_MS = 30
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_MS / 1000)


def longest_run(levels, threshold):
    best = 0
    current = 0
    for level in levels:
        if level > threshold:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def main():
    parser = argparse.ArgumentParser(description="Mic level monitor (VAD diagnose)")
    parser.add_argument("--device", type=int, default=None, help="mic device number")
    parser.add_argument("--seconds", type=int, default=8, help="monitor seconds")
    args = parser.parse_args()

    audio_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_queue.put(indata[:, 0].copy())

    levels = []
    window = []
    start = time.perf_counter()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SIZE,
        device=args.device,
        callback=callback,
    ):
        print("Mic levels kaattren... mudhal 2 seconds amaidhiya iru, appuram pesu.\n")
        while time.perf_counter() - start < args.seconds:
            try:
                block = audio_queue.get(timeout=2.0)
            except queue.Empty:
                print("Mic la irundhu audio varala (device check pannu).")
                break

            rms = float(np.sqrt(np.mean(np.square(block))))
            levels.append(rms)
            window.append(rms)

            if len(window) >= 3:
                level = max(window)
                window = []
                bar = "#" * min(60, int(level * 600))
                elapsed = time.perf_counter() - start
                print(f"{elapsed:4.1f}s  rms={level:.4f}  {bar}")

    if not levels:
        print("\nEdhuvum record aagala.")
        return

    print("\n--- SUMMARY ---")
    print(f"Blocks (30ms)        : {len(levels)}")
    print(f"Max rms              : {max(levels):.4f}")
    print(f"Blocks > 0.003       : {sum(1 for x in levels if x > 0.003)}")
    print(f"Blocks > 0.010       : {sum(1 for x in levels if x > 0.010)}")
    print(f"Longest run > 0.003  : {longest_run(levels, 0.003)} blocks (3 venum)")
    print(f"Longest run > 0.010  : {longest_run(levels, 0.010)} blocks (3 venum)")


if __name__ == "__main__":
    main()