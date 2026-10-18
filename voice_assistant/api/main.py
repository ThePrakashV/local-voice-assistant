import asyncio
import json
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from voice_assistant.config import APP_HOST, APP_PORT, AUDIO_DIR
from voice_assistant.monitoring import metrics
from voice_assistant.monitoring.dashboard import render_html
from voice_assistant.pipeline import REPLY_DIR, VoicePipeline

UPLOAD_DIR = AUDIO_DIR / "uploads"
TERMINAL_EVENTS = ("done", "error", "cancelled")
state = {}


@asynccontextmanager
async def lifespan(app):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading pipeline (Whisper + Piper)...")
    state["pipeline"] = VoicePipeline()
    print("Pipeline ready.")
    yield
    state.clear()


app = FastAPI(title="Voice Assistant API", version="0.9.0", lifespan=lifespan)


class TextRequest(BaseModel):
    text: str


def save_upload(upload):
    suffix = Path(upload.filename or "").suffix or ".wav"
    path = UPLOAD_DIR / f"upload_{uuid.uuid4().hex[:8]}{suffix}"
    with open(path, "wb") as file:
        shutil.copyfileobj(upload.file, file)
    return path


def save_audio_bytes(data):
    path = UPLOAD_DIR / f"ws_{uuid.uuid4().hex[:8]}.wav"
    path.write_bytes(data)
    return path


@app.get("/health")
def health():
    pipeline = state["pipeline"]
    return {
        "status": "ok",
        "llm_model": pipeline.llm.model,
        "tts_voice": pipeline.synthesizer.voice_name,
    }


@app.get("/metrics")
def get_metrics(limit: int = 100):
    return metrics.load_records(limit=limit)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(limit: int = 100, refresh: int = 0):
    records = metrics.load_records(limit=limit)
    return HTMLResponse(render_html(records, refresh_seconds=refresh or None))


@app.post("/chat")
def chat(request: TextRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text empty ah irukku")
    try:
        return state["pipeline"].chat(request.text)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@app.post("/reset")
def reset():
    state["pipeline"].reset()
    return {"status": "history cleared"}


@app.post("/stt")
def stt(file: UploadFile = File(...), language: str | None = Form(None)):
    audio_path = save_upload(file)
    return state["pipeline"].transcribe(audio_path, language=language or None)


@app.post("/tts")
def tts(request: TextRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text empty ah irukku")
    result = state["pipeline"].speak(request.text)
    return FileResponse(result["path"], media_type="audio/wav", filename=result["filename"])


@app.post("/voice")
def voice(file: UploadFile = File(...), language: str | None = Form(None)):
    audio_path = save_upload(file)
    try:
        result = state["pipeline"].voice(audio_path, language=language or None)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    metrics.record_turn("done", "rest", result["timings"])
    result["audio_url"] = f"/audio/{result['audio_file']}"
    return result


@app.get("/audio/{filename}")
def get_audio(filename: str):
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = REPLY_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio file illa")
    return FileResponse(path, media_type="audio/wav")


async def send_event(websocket, event):
    audio = event.pop("audio", None)
    await websocket.send_text(json.dumps(event))
    if audio is not None:
        await websocket.send_bytes(audio)


async def stream_events(emit, make_generator, cancel_event):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def worker():
        try:
            generator = make_generator()
            for event in generator:
                if cancel_event.is_set():
                    generator.close()
                    loop.call_soon_threadsafe(queue.put_nowait, {"type": "cancelled"})
                    return
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as error:
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "message": str(error)}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = await queue.get()
        if event is None:
            break
        if cancel_event.is_set() and event.get("type") not in TERMINAL_EVENTS:
            continue
        if event.get("type") == "cancelled":
            print("Turn cancelled (interrupt)")
        await emit(event)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    pipeline = state["pipeline"]
    session = pipeline.new_session()
    language = None
    turn_task = None
    cancel_event = threading.Event()
    send_lock = asyncio.Lock()
    print("WebSocket client connected")

    async def emit(event):
        kind = event.get("type")
        if kind == "done":
            metrics.record_turn("done", "ws", event.get("timings"))
        elif kind == "cancelled":
            metrics.record_turn("cancelled", "ws")

        async with send_lock:
            await send_event(websocket, event)

    async def run_turn(turn_cancel, audio_path, text, turn_language):
        try:
            await stream_events(
                emit,
                lambda: pipeline.stream_turn(
                    session,
                    audio_path=audio_path,
                    text=text,
                    language=turn_language,
                ),
                turn_cancel,
            )
        finally:
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)

    async def cancel_running_turn():
        nonlocal turn_task
        if turn_task is None:
            return
        if not turn_task.done():
            cancel_event.set()
        try:
            await turn_task
        except Exception as error:
            print(f"Turn error: {error}")
        turn_task = None

    async def start_turn(audio_path=None, text=None):
        nonlocal turn_task, cancel_event
        await cancel_running_turn()
        cancel_event = threading.Event()
        turn_task = asyncio.create_task(
            run_turn(cancel_event, audio_path, text, language)
        )

    try:
        await emit(
            {
                "type": "ready",
                "llm_model": session.model,
                "tts_voice": pipeline.synthesizer.voice_name,
            }
        )

        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                await start_turn(audio_path=save_audio_bytes(message["bytes"]))

            elif message.get("text") is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await emit({"type": "error", "message": "invalid JSON"})
                    continue

                kind = data.get("type")

                if kind == "config":
                    language = data.get("language") or None
                    await emit({"type": "config_ok", "language": language})
                elif kind == "text":
                    text = (data.get("text") or "").strip()
                    if not text:
                        await emit({"type": "error", "message": "text empty ah irukku"})
                    else:
                        await start_turn(text=text)
                elif kind == "cancel":
                    await cancel_running_turn()
                elif kind == "reset":
                    await cancel_running_turn()
                    session.reset()
                    await emit({"type": "reset_ok"})
                else:
                    await emit({"type": "error", "message": f"unknown type: {kind}"})

    except (WebSocketDisconnect, RuntimeError) as error:
        print(f"WebSocket closed: {error}")
    finally:
        cancel_event.set()
        if turn_task is not None:
            try:
                await turn_task
            except Exception:
                pass
        print("WebSocket client disconnected")


if __name__ == "__main__":
    uvicorn.run("voice_assistant.api.main:app", host=APP_HOST, port=APP_PORT)