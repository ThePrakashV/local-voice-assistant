import sys

import httpx

from voice_assistant.config import PIPER_VOICE, VOICES_DIR

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def voice_urls(voice_name):
    locale, speaker, quality = voice_name.split("-")
    language = locale.split("_")[0]
    folder = f"{BASE_URL}/{language}/{locale}/{speaker}/{quality}/{voice_name}"
    return [f"{folder}.onnx", f"{folder}.onnx.json"]


def download_file(url, destination):
    if destination.exists():
        print(f"Already irukku: {destination.name}")
        return

    print(f"Downloading {destination.name} ...")
    temp_path = destination.with_suffix(destination.suffix + ".part")

    with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Download fail ({response.status_code}): {url}")

        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        with open(temp_path, "wb") as file:
            for chunk in response.iter_bytes(chunk_size=1024 * 256):
                file.write(chunk)
                downloaded += len(chunk)
                if total:
                    percent = downloaded * 100 // total
                    print(f"\r  {percent}% ({downloaded // (1024 * 1024)} MB)", end="", flush=True)
        print()

    temp_path.rename(destination)
    print(f"Saved: {destination}")


def main():
    voice_name = sys.argv[1] if len(sys.argv) > 1 else PIPER_VOICE
    VOICES_DIR.mkdir(parents=True, exist_ok=True)

    for url in voice_urls(voice_name):
        file_name = url.split("/")[-1]
        download_file(url, VOICES_DIR / file_name)

    print(f"\nVoice ready: {voice_name}")


if __name__ == "__main__":
    main()