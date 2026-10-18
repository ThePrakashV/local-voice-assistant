import json
import threading
from datetime import datetime

from voice_assistant.config import ROOT_DIR

LOG_DIR = ROOT_DIR / "logs"
METRICS_FILE = LOG_DIR / "metrics.jsonl"

_lock = threading.Lock()


def record_turn(status, source, timings=None):
    timings = timings or {}
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "source": source,
        "fallback": status == "done" and not timings.get("llm_total"),
        "timings": timings,
    }

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(METRICS_FILE, "a", encoding="utf-8") as file:
                file.write(json.dumps(entry) + "\n")
    except OSError as error:
        print(f"Metrics write fail aachu: {error}")


def load_records(limit=None):
    if not METRICS_FILE.exists():
        return []

    with _lock:
        with open(METRICS_FILE, "r", encoding="utf-8") as file:
            lines = file.readlines()

    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if limit:
        records = records[-limit:]
    return records