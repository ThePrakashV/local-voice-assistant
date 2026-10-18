import argparse

from voice_assistant.stt.vad_recorder import record_until_silence

STATUS_TEXT = {
    "silence": "Silence detect aachu, auto-stop aachu (correct)",
    "no_speech": "Speech detect aagala (threshold romba athigam irukkalaam)",
    "max_length": "Max seconds varaikkum record aachu (silence detect aagala)",
    "no_audio": "Mic la irundhu audio varala (device number check pannu)",
}


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant VAD recorder test")
    parser.add_argument("--device", type=int, default=None, help="mic device number")
    parser.add_argument("--silence", type=float, default=None, help="evlo seconds silence na stop")
    parser.add_argument("--max-seconds", type=float, default=None, help="max recording seconds")
    parser.add_argument("--multiplier", type=float, default=None, help="threshold = noise x multiplier")
    parser.add_argument("--min-threshold", type=float, default=None, help="minimum threshold")
    parser.add_argument("--transcribe", action="store_true", help="record pannitu Whisper la text-a maathu")
    parser.add_argument("--language", type=str, default=None, help="en, ta...")
    args = parser.parse_args()

    result = record_until_silence(
        device=args.device,
        silence_seconds=args.silence,
        max_seconds=args.max_seconds,
        multiplier=args.multiplier,
        min_threshold=args.min_threshold,
    )

    print("\n--- RESULT ---")
    print(f"Status    : {result['status']} -> {STATUS_TEXT.get(result['status'], '')}")
    print(f"Duration  : {result['duration']}s")
    print(f"Noise     : {result['noise']}")
    print(f"Threshold : {result['threshold']}")
    print(f"Peak      : {result['peak']}")
    print(f"Saved     : {result['path']}")

    if args.transcribe and result["path"]:
        from voice_assistant.stt.transcriber import Transcriber

        transcriber = Transcriber()
        stt = transcriber.transcribe(result["path"], language=args.language)
        print("\n--- TRANSCRIPT ---")
        print(f"Text      : {stt['text']}")
        print(f"Language  : {stt['language']} ({stt['language_probability']})")
        print(f"Process   : {stt['processing_time']}s")


if __name__ == "__main__":
    main()