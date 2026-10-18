import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class SentenceSplitter:
    def __init__(self, min_chars=12):
        self.buffer = ""
        self.min_chars = min_chars

    def feed(self, token):
        self.buffer += token
        sentences = []

        while True:
            cut = None
            for match in SENTENCE_END.finditer(self.buffer):
                if match.start() >= self.min_chars:
                    cut = match
                    break

            if cut is None:
                break

            sentences.append(self.buffer[: cut.start()].strip())
            self.buffer = self.buffer[cut.end():]

        return sentences

    def flush(self):
        rest = self.buffer.strip()
        self.buffer = ""
        return [rest] if rest else []