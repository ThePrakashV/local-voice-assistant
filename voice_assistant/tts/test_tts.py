import argparse

import sounddevice as sd

from voice_assistant.tts.synthesizer import Synthesizer

DEFAULT_TEXT = "Hello Prakash, I am your voice assistant. How can I help you today?"


def list_output_devices():
    hostapis = sd.query_hostapis()
    for index, device in enumerate(sd.query_devices()):
        if device["max_output_channels"] > 0:
            api_name = hostapis[device["hostapi"]]["name"]
            print(f"[{index}] {device['name']} | {api_name}")


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant TTS test")
    parser.add_argument("--list-out", action="store_true", help="speaker devices list kaattu")
    parser.add_argument("--text", type=str, default=DEFAULT_TEXT, help="pesa vendiya text")
    parser.add_argument("--voice", type=str, default=None, help="piper voice name")
    parser.add_argument("--out-device", type=int, default=None, help="speaker device number")
    parser.add_argument("--no-play", action="store_true", help="file mattum save pannu, play pannaadhe")
    args = parser.parse_args()

    if args.list_out:
        list_output_devices()
        return

    try:
        if args.voice:
            synthesizer = Synthesizer(voice_name=args.voice)
        else:
            synthesizer = Synthesizer()
    except FileNotFoundError as error:
        print(f"ERROR: {error}")
        return

    result = synthesizer.synthesize_to_file(args.text)

    print("\n--- RESULT ---")
    print(f"Voice     : {synthesizer.voice_name}")
    print(f"Saved     : {result['path']}")
    print(f"Audio len : {result['audio_duration']}s")
    print(f"Process   : {result['processing_time']}s")
    print(f"RTF       : {result['rtf']} (1-ku kuraiya irundha real-time ku OK)")

    if not args.no_play:
        print("\nPlaying...")
        synthesizer.play(result["path"], device=args.out_device)
        print("Play mudinjuchu.")


if __name__ == "__main__":
    main()