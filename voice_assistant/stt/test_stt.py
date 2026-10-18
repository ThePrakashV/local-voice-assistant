import argparse

from voice_assistant.stt.recorder import list_input_devices, record
from voice_assistant.stt.transcriber import Transcriber


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant STT test")
    parser.add_argument("--list", action="store_true", help="mic devices list kaattu")
    parser.add_argument("--seconds", type=int, default=5, help="record seconds")
    parser.add_argument("--device", type=int, default=None, help="mic device number")
    parser.add_argument("--file", type=str, default=None, help="existing audio file path")
    parser.add_argument("--language", type=str, default=None, help="en, ta, hi...")
    parser.add_argument("--model", type=str, default=None, help="tiny, base, small...")
    args = parser.parse_args()

    if args.list:
        list_input_devices()
        return

    if args.file:
        audio_path = args.file
    else:
        audio_path, peak = record(seconds=args.seconds, device=args.device)
        print(f"Saved: {audio_path} | peak volume: {peak:.3f}")
        if peak < 0.01:
            print("WARNING: Volume romba kuraivu. Wrong mic device irukkalam.")

    if args.model:
        transcriber = Transcriber(model_size=args.model)
    else:
        transcriber = Transcriber()

    result = transcriber.transcribe(audio_path, language=args.language)

    print("\n--- RESULT ---")
    print(f"Text      : {result['text']}")
    print(f"Language  : {result['language']} ({result['language_probability']})")
    print(f"Audio len : {result['audio_duration']}s")
    print(f"Process   : {result['processing_time']}s")


if __name__ == "__main__":
    main()