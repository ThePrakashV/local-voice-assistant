import argparse
from pathlib import Path

import httpx
import sounddevice as sd
import soundfile as sf

from voice_assistant.config import APP_PORT, AUDIO_DIR
from voice_assistant.stt.recorder import record

BASE_URL = f"http://127.0.0.1:{APP_PORT}"


def play_wav(path, device=None):
    data, sample_rate = sf.read(str(path), dtype="float32")
    sd.play(data, sample_rate, device=device)
    sd.wait()


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant API test client")
    parser.add_argument("--file", type=str, default=None, help="existing audio file")
    parser.add_argument("--seconds", type=int, default=5, help="record seconds")
    parser.add_argument("--device", type=int, default=None, help="mic device number")
    parser.add_argument("--out-device", type=int, default=None, help="speaker device number")
    parser.add_argument("--language", type=str, default=None, help="en, ta...")
    parser.add_argument("--no-play", action="store_true", help="reply play pannaadhe")
    args = parser.parse_args()

    if args.file:
        audio_path = Path(args.file)
    else:
        audio_path, peak = record(seconds=args.seconds, device=args.device, filename="client_input.wav")
        print(f"Recorded: {audio_path} | peak volume: {peak:.3f}")

    data = {"language": args.language} if args.language else {}

    try:
        with open(audio_path, "rb") as audio_file:
            files = {"file": (audio_path.name, audio_file, "audio/wav")}
            response = httpx.post(f"{BASE_URL}/voice", files=files, data=data, timeout=300.0)
    except httpx.ConnectError:
        print("ERROR: Server connect aagala. Mudhal la server start pannu (vera CMD window la).")
        return

    if response.status_code != 200:
        print(f"ERROR {response.status_code}: {response.text}")
        return

    result = response.json()
    timings = result["timings"]

    print("\n--- RESULT ---")
    print(f"You said  : {result['user_text']}")
    print(f"Language  : {result['detected_language']}")
    print(f"Assistant : {result['reply_text']}")
    print(
        f"Timings   : stt={timings['stt']}s | llm first token={timings['llm_first_token']}s | "
        f"llm total={timings['llm_total']}s | tts={timings['tts']}s | total={timings['total']}s"
    )

    reply_path = AUDIO_DIR / "client_reply.wav"
    audio_response = httpx.get(f"{BASE_URL}{result['audio_url']}", timeout=60.0)
    reply_path.write_bytes(audio_response.content)
    print(f"Reply saved: {reply_path}")

    if not args.no_play:
        print("Playing reply...")
        play_wav(reply_path, device=args.out_device)
        print("Play mudinjuchu.")


if __name__ == "__main__":
    main()