"""Vietnamese sentence splitter for streaming LLM output.

Splits incoming token stream into complete sentences so TTS can start
synthesizing the first sentence while LLM is still generating the rest.

Yield rules (priority order):
  1. [.!?…\\n] — always yield (hard boundary)
  2. [,;] + buffer >= min_chars — clause end
  3. ends with ("ạ,"|"nhé,"|"nha,") + buffer >= min_chars — Vietnamese clause end
  4. buffer >= 100 chars → yield at next SPACE (never mid-word)
"""

from __future__ import annotations

import re

_HARD_BOUNDARY = re.compile(
    r"(?<=[.!?…])\s+"
    r"|(?<=ạ\.)\s*"
    r"|(?<=ạ!)\s*"
    r"|(?<=nhé\.)\s*"
    r"|(?<=nhé!)\s*"
    r"|\n"
)

_FORCE_SPLIT_CHARS = 100  # rule 4: force yield after this many chars


class SentenceSplitter:
    """Feed tokens one at a time; call .feed() to get emitted sentences.

    Example:
        splitter = SentenceSplitter(min_chars=30)
        for token in llm_stream:
            for sentence in splitter.feed(token):
                yield sentence
        for sentence in splitter.flush():
            yield sentence
    """

    def __init__(self, min_chars: int = 30) -> None:
        self._min = min_chars
        self._buffer: str = ""

    def feed(self, token: str) -> list[str]:
        self._buffer += token
        return self._split_buffer()

    def flush(self) -> list[str]:
        text = self._buffer.strip()
        self._buffer = ""
        return [text] if len(text) >= self._min else []

    def _split_buffer(self) -> list[str]:
        results: list[str] = []

        while True:
            # Rule 1: hard boundary
            m = _HARD_BOUNDARY.search(self._buffer)
            if m:
                part = self._buffer[: m.start()].strip()
                self._buffer = self._buffer[m.end():]
                if len(part) >= self._min:
                    results.append(part)
                continue

            # Rule 4: force split at word boundary when buffer too long
            if len(self._buffer) >= _FORCE_SPLIT_CHARS:
                # Find the next space after position 0 to avoid mid-word cut
                space_idx = self._buffer.find(" ", self._min)
                if space_idx != -1:
                    part = self._buffer[:space_idx].strip()
                    self._buffer = self._buffer[space_idx + 1:]
                    if len(part) >= self._min:
                        results.append(part)
                    continue

            # Rule 2: comma/semicolon + length
            if len(self._buffer) >= self._min:
                stripped = self._buffer.rstrip()
                if stripped and stripped[-1] in (",", ";"):
                    results.append(self._buffer.strip())
                    self._buffer = ""
                    break

            # Rule 3: Vietnamese soft boundary
            if len(self._buffer) >= self._min:
                for suffix in ("ạ,", "nhé,", "nha,"):
                    if self._buffer.rstrip().endswith(suffix):
                        results.append(self._buffer.strip())
                        self._buffer = ""
                        break
                else:
                    break
                continue

            break

        return results
