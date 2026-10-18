import argparse
import io
import json
import queue
import threading
import time

import sounddevice as sd
import soundfile as sf
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from voice_assistant.config import APP_PORT
from voice_assistant.stt.recorder import record

WS_URL = f"ws://127.0.0.1:{APP_PORT}/ws"


class Player:
    def __init__(self, device=None, enabled=True):
        self.device = device
        self.enabled = enabled
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            try:
                data, sample_rate = sf.read(io.BytesIO(item), dtype="float32")
                sd.play(data, sample_rate, device=self.device)
                sd.wait()
            except Exception as error:
                print(f"\n[playback error] {error}")
            finally:
                self.queue.task_done()

    def add(self, wav_bytes):
        if self.enabled:
            self.queue.put(wav_bytes)

    def wait_until_done(self):
        self.queue.join()

    def stop(self):
        self.queue.put(None)


def receive_turn(ws, player, start_time):
    first_audio = None
    started = False

    while True:
        message = ws.recv(timeout=300)

        if isinstance(message, bytes):
            if first_audio is None:
                first_audio = time.perf_counter() - start_time
            player.add(message)
            continue

        event = json.loads(message)
        kind = event.get("type")

        if kind == "transcript":
            print(f"You said  : {event['text']} ({event['language']})")
        elif kind == "token":
            if not started:
                print("Assistant : ", end="", flush=True)
                started = True
            print(event["text"], end="", flush=True)
        elif kind == "done":
            timings = event["timings"]
            print(
                f"\nTimings   : stt={timings['stt']}s | llm first token={timings['llm_first_token']}s | "
                f"llm total={timings['llm_total']}s | tts={timings['tts']}s | "
                f"server first audio={timings['first_audio']}s | total={timings['total']}s"
            )
            if first_audio is not None:
                print(f"Client    : first audio received after {first_audio:.2f}s")
            return
        elif kind == "error":
            print(f"\nERROR: {event['message']}")
            return


def do_turn(ws, player, text=None, seconds=5, device=None):
    if text:
        start = time.perf_counter()
        ws.send(json.dumps({"type": "text", "text": text}))
    else:
        audio_path, peak = record(
            seconds=seconds, device=device, filename="ws_client_input.wav"
        )
        print(f"Recorded | peak volume: {peak:.3f}")
        audio_bytes = audio_path.read_bytes()
        start = time.perf_counter()
        ws.send(audio_bytes)

    receive_turn(ws, player, start)
    player.wait_until_done()


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant WebSocket client")
    parser.add_argument("--text", type=str, default=None, help="single typed message")
    parser.add_argument("--chat", action="store_true", help="multi-turn mode (same connection)")
    parser.add_argument("--seconds", type=int, default=5, help="record seconds")
    parser.add_argument("--device", type=int, default=None, help="mic device number")
    parser.add_argument("--out-device", type=int, default=None, help="speaker device number")
    parser.add_argument("--language", type=str, default=None, help="en, ta...")
    parser.add_argument("--no-play", action="store_true", help="audio play pannaadhe")
    args = parser.parse_args()

    player = Player(device=args.out_device, enabled=not args.no_play)

    try:
        with connect(WS_URL, max_size=None) as ws:
            ready = json.loads(ws.recv(timeout=30))
            print(f"Connected | model={ready['llm_model']} | voice={ready['tts_voice']}")

            if args.language:
                ws.send(json.dumps({"type": "config", "language": args.language}))
                ws.recv(timeout=30)

            if not args.chat:
                do_turn(ws, player, text=args.text, seconds=args.seconds, device=args.device)
                return

            print("\nChat mode: Enter = mic la pesu | text type pannu = text anuppu | r = reset | q = quit")
            while True:
                choice = input("\n> ").strip()
                if choice.lower() == "q":
                    break
                if choice.lower() == "r":
                    ws.send(json.dumps({"type": "reset"}))
                    ws.recv(timeout=30)
                    print("History clear aachu.")
                    continue
                do_turn(
                    ws,
                    player,
                    text=choice or None,
                    seconds=args.seconds,
                    device=args.device,
                )

    except ConnectionRefusedError:
        print("ERROR: Server connect aagala. Mudhal la server start pannu (vera CMD window la).")
    except ConnectionClosed as error:
        print(f"ERROR: Server connection close aachu: {error}")
    finally:
        player.stop()


if __name__ == "__main__":
    main()