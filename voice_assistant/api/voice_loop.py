import argparse
import collections
import io
import json
import queue
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from voice_assistant.config import (
    APP_PORT,
    SAMPLE_RATE,
    VAD_MAX_SECONDS,
    VAD_MIN_THRESHOLD,
    VAD_MULTIPLIER,
    VAD_SILENCE_SECONDS,
)

WS_URL = f"ws://127.0.0.1:{APP_PORT}/ws"

BLOCK_MS = 30
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_MS / 1000)
CALIBRATION_BLOCKS = 17
PRE_ROLL_BLOCKS = 10
START_BLOCKS = 3
TAIL_BLOCKS = 10
MIN_SPEECH_BLOCKS = 13
COOLDOWN_BLOCKS = 10


def block_rms(block):
    return float(np.sqrt(np.mean(np.square(block))))


def encode_wav(audio):
    buffer = io.BytesIO()
    sf.write(buffer, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


class Player:
    def __init__(self, device=None, enabled=True):
        self.device = device
        self.enabled = enabled
        self.queue = queue.Queue()
        self.generation = 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while True:
            generation, wav_bytes = self.queue.get()
            try:
                if wav_bytes is None:
                    return
                if generation != self.generation:
                    continue
                data, sample_rate = sf.read(io.BytesIO(wav_bytes), dtype="float32")
                sd.play(data, sample_rate, device=self.device)
                while generation == self.generation and sd.get_stream().active:
                    time.sleep(0.02)
                if generation != self.generation:
                    sd.stop()
            except Exception as error:
                print(f"\n[playback error] {error}")
            finally:
                self.queue.task_done()

    def add(self, wav_bytes):
        if self.enabled:
            self.queue.put((self.generation, wav_bytes))

    def busy(self):
        return self.queue.unfinished_tasks > 0

    def clear(self):
        self.generation += 1
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
            self.queue.task_done()
        try:
            sd.stop()
        except Exception:
            pass

    def stop(self):
        self.queue.put((0, None))


class LoopState:
    def __init__(self):
        self.lock = threading.Lock()
        self.sent = 0
        self.finished = 0
        self.cancelled = set()
        self.sent_time = {}


def receive_events(ws, player, state, stop_event):
    streaming_idx = None
    first_audio = {}

    while not stop_event.is_set():
        try:
            message = ws.recv(timeout=1.0)
        except TimeoutError:
            continue
        except ConnectionClosed:
            if not stop_event.is_set():
                print("\nServer connection close aachu.")
            stop_event.set()
            return

        with state.lock:
            idx = state.finished
            dropped = idx in state.cancelled
            sent_at = state.sent_time.get(idx)

        if isinstance(message, bytes):
            if dropped:
                continue
            if idx not in first_audio and sent_at is not None:
                first_audio[idx] = time.perf_counter() - sent_at
            player.add(message)
            continue

        event = json.loads(message)
        kind = event.get("type")

        if kind in ("done", "error", "cancelled"):
            with state.lock:
                state.finished += 1
                state.cancelled.discard(idx)
                state.sent_time.pop(idx, None)
            latency = first_audio.pop(idx, None)
            streaming_idx = None

            if dropped:
                continue
            if kind == "done":
                timings = event["timings"]
                print(
                    f"\nTimings   : stt={timings['stt']}s | llm first token={timings['llm_first_token']}s | "
                    f"llm total={timings['llm_total']}s | tts={timings['tts']}s | "
                    f"server first audio={timings['first_audio']}s | total={timings['total']}s"
                )
                if latency is not None:
                    print(f"Client    : first audio {latency:.2f}s after you stopped speaking")
            elif kind == "error":
                print(f"\nERROR: {event.get('message')}")
            continue

        if dropped:
            continue

        if kind == "transcript":
            print(f"\nYou said  : {event['text']} ({event['language']})")
        elif kind == "token":
            if streaming_idx != idx:
                print("Assistant : ", end="", flush=True)
                streaming_idx = idx
            print(event["text"], end="", flush=True)


def finish_recording(ws, state, recorded, silent):
    extra = silent - TAIL_BLOCKS
    blocks = recorded[:-extra] if extra > 0 else recorded

    if len(blocks) < MIN_SPEECH_BLOCKS:
        print("(romba chinna sathham, ignore pannen)")
        return False

    audio = np.concatenate(blocks)
    duration = len(audio) / SAMPLE_RATE
    payload = encode_wav(audio)

    with state.lock:
        idx = state.sent
        state.sent += 1
        state.sent_time[idx] = time.perf_counter()

    ws.send(payload)
    print(f"Sent {duration:.1f}s audio. Processing...")
    return True


def interrupt(ws, player, state):
    with state.lock:
        active = state.finished < state.sent
        if active:
            state.cancelled.update(range(state.finished, state.sent))
    player.clear()
    if active:
        ws.send(json.dumps({"type": "cancel"}))


def run_loop(ws, args, player, state, stop_event):
    mic_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        mic_queue.put(indata[:, 0].copy())

    silence_limit = max(1, int(args.silence * 1000 / BLOCK_MS))
    max_blocks = int(args.max_seconds * 1000 / BLOCK_MS)
    pre_roll = collections.deque(maxlen=max(PRE_ROLL_BLOCKS, args.interrupt_blocks + 6))

    mode = "LISTENING"
    speech_run = 0
    interrupt_run = 0
    silent = 0
    cooldown = 0
    recorded = []

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SIZE,
        device=args.device,
        callback=callback,
    ):
        print("Background noise calibrate pannren... amaidhiya iru (0.5s)")
        noise_levels = []
        while len(noise_levels) < CALIBRATION_BLOCKS:
            try:
                noise_levels.append(block_rms(mic_queue.get(timeout=2.0)))
            except queue.Empty:
                print("ERROR: Mic la irundhu audio varala (device number check pannu).")
                return

        noise = float(np.median(noise_levels))
        threshold = max(noise * args.multiplier, args.threshold)
        if args.interrupt_threshold is None:
            interrupt_threshold = max(threshold * 4, 0.02)
        else:
            interrupt_threshold = args.interrupt_threshold

        print(f"Noise={noise:.4f} | speech threshold={threshold:.4f}")
        if args.interrupt:
            print(
                f"Interrupt ON | threshold={interrupt_threshold:.4f} | "
                f"blocks={args.interrupt_blocks} ({args.interrupt_blocks * BLOCK_MS}ms)"
            )
        else:
            print("Interrupt OFF")
        print("\nHands-free mode ready. Pesu... (Ctrl+C = exit)")

        while not stop_event.is_set():
            try:
                block = mic_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            level = block_rms(block)
            pre_roll.append(block)

            if mode == "WAITING":
                with state.lock:
                    active = state.finished < state.sent

                if not active and not player.busy():
                    mode = "LISTENING"
                    speech_run = 0
                    interrupt_run = 0
                    cooldown = COOLDOWN_BLOCKS
                    print("\n[Listening... pesu]")
                    continue

                if args.interrupt:
                    interrupt_run = interrupt_run + 1 if level > interrupt_threshold else 0
                    if interrupt_run >= args.interrupt_blocks:
                        interrupt(ws, player, state)
                        mode = "RECORDING"
                        recorded = list(pre_roll)
                        silent = 0
                        interrupt_run = 0
                        print("\n[INTERRUPT] Reply nirutthitten. Nee pesu...")

            elif mode == "LISTENING":
                if cooldown > 0:
                    cooldown -= 1
                    continue

                speech_run = speech_run + 1 if level > threshold else 0
                if speech_run >= START_BLOCKS:
                    mode = "RECORDING"
                    recorded = list(pre_roll)
                    silent = 0
                    speech_run = 0
                    print("[Recording...]")

            elif mode == "RECORDING":
                recorded.append(block)
                if level > threshold:
                    silent = 0
                else:
                    silent += 1

                if silent >= silence_limit or len(recorded) >= max_blocks:
                    if finish_recording(ws, state, recorded, silent):
                        mode = "WAITING"
                        interrupt_run = 0
                    else:
                        mode = "LISTENING"
                        cooldown = COOLDOWN_BLOCKS
                    recorded = []
                    silent = 0


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant hands-free loop")
    parser.add_argument("--device", type=int, default=None, help="mic device number")
    parser.add_argument("--out-device", type=int, default=None, help="speaker device number")
    parser.add_argument("--language", type=str, default=None, help="en, ta...")
    parser.add_argument("--silence", type=float, default=VAD_SILENCE_SECONDS, help="stop panna silence seconds")
    parser.add_argument("--max-seconds", type=float, default=VAD_MAX_SECONDS, help="oru utterance max seconds")
    parser.add_argument("--threshold", type=float, default=VAD_MIN_THRESHOLD, help="min speech threshold")
    parser.add_argument("--multiplier", type=float, default=VAD_MULTIPLIER, help="threshold = noise x multiplier")
    parser.add_argument("--no-interrupt", dest="interrupt", action="store_false", help="interrupt OFF")
    parser.add_argument("--interrupt-threshold", type=float, default=None, help="interrupt rms threshold")
    parser.add_argument("--interrupt-blocks", type=int, default=8, help="thodarchiya blocks (1 block = 30ms)")
    parser.add_argument("--no-play", action="store_true", help="audio play pannaadhe")
    parser.set_defaults(interrupt=True)
    args = parser.parse_args()

    player = Player(device=args.out_device, enabled=not args.no_play)
    state = LoopState()
    stop_event = threading.Event()

    try:
        with connect(WS_URL, max_size=None) as ws:
            ready = json.loads(ws.recv(timeout=30))
            print(f"Connected | model={ready['llm_model']} | voice={ready['tts_voice']}")

            if args.language:
                ws.send(json.dumps({"type": "config", "language": args.language}))
                ws.recv(timeout=30)

            receiver = threading.Thread(
                target=receive_events, args=(ws, player, state, stop_event), daemon=True
            )
            receiver.start()

            try:
                run_loop(ws, args, player, state, stop_event)
            finally:
                stop_event.set()
                receiver.join(timeout=3)

    except ConnectionRefusedError:
        print("ERROR: Server connect aagala. Mudhal la server start pannu (vera CMD window la).")
    except ConnectionClosed as error:
        print(f"ERROR: Server connection close aachu: {error}")
    except KeyboardInterrupt:
        print("\nBye!")
    finally:
        player.clear()
        player.stop()


if __name__ == "__main__":
    main()