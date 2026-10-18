import json
import time

import httpx

from voice_assistant.config import (
    MAX_HISTORY,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
)

SYSTEM_PROMPT = (
    "You are a friendly voice assistant. "
    "Replies are read aloud: use 1 to 3 short plain sentences, "
    "no markdown, lists or emojis. "
    "Reply in the user's language."
)


class OllamaClient:
    def __init__(
        self,
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        system_prompt=SYSTEM_PROMPT,
        max_history=MAX_HISTORY,
        keep_alive=OLLAMA_KEEP_ALIVE,
        num_ctx=OLLAMA_NUM_CTX,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.history = []
        self.last_stats = {}

    def reset(self):
        self.history = []
        self.last_stats = {}

    def _build_messages(self):
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        return messages

    def _trim_history(self):
        limit = self.max_history * 2
        if len(self.history) > limit:
            self.history = self.history[-limit:]

    def warmup(self):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": "Hi"},
            ],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": 1, "num_ctx": self.num_ctx},
        }

        start = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat", json=payload, timeout=180.0
            )
        except httpx.HTTPError as error:
            raise RuntimeError(f"Ollama warm-up fail: {error}")

        if response.status_code != 200:
            raise RuntimeError(f"Ollama error {response.status_code}: {response.text}")

        return round(time.perf_counter() - start, 2)

    def chat_stream(self, user_text):
        self.history.append({"role": "user", "content": user_text})
        self._trim_history()

        payload = {
            "model": self.model,
            "messages": self._build_messages(),
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.7,
                "num_predict": 256,
                "num_ctx": self.num_ctx,
            },
        }

        url = f"{self.base_url}/api/chat"
        start = time.perf_counter()
        first_token_time = None
        reply_parts = []
        final_chunk = {}

        try:
            with httpx.stream("POST", url, json=payload, timeout=120.0) as response:
                if response.status_code != 200:
                    body = response.read().decode("utf-8", errors="replace")
                    self.history.pop()
                    raise RuntimeError(f"Ollama error {response.status_code}: {body}")

                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        if first_token_time is None:
                            first_token_time = time.perf_counter() - start
                        reply_parts.append(token)
                        yield token
                    if chunk.get("done"):
                        final_chunk = chunk
                        break
        except GeneratorExit:
            partial = "".join(reply_parts).strip()
            if partial:
                self.history.append({"role": "assistant", "content": partial})
                self._trim_history()
            else:
                self.history.pop()
            raise
        except httpx.ConnectError:
            self.history.pop()
            raise RuntimeError(
                f"Ollama connect aagala ({self.base_url}). Ollama running ah nu check pannu."
            )

        reply = "".join(reply_parts).strip()
        self.history.append({"role": "assistant", "content": reply})
        self._trim_history()

        total_time = time.perf_counter() - start
        eval_count = final_chunk.get("eval_count", 0)
        eval_duration = final_chunk.get("eval_duration", 0) / 1e9
        tokens_per_sec = round(eval_count / eval_duration, 1) if eval_duration > 0 else 0.0

        self.last_stats = {
            "model": self.model,
            "first_token_latency": round(first_token_time or 0.0, 2),
            "total_time": round(total_time, 2),
            "tokens": eval_count,
            "tokens_per_sec": tokens_per_sec,
            "prompt_tokens": final_chunk.get("prompt_eval_count", 0),
            "prompt_eval_time": round(final_chunk.get("prompt_eval_duration", 0) / 1e9, 2),
            "load_time": round(final_chunk.get("load_duration", 0) / 1e9, 2),
        }

    def chat(self, user_text):
        return "".join(self.chat_stream(user_text)).strip()