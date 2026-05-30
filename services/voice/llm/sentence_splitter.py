"""Vietnamese sentence splitter for streaming LLM output.

Splits incoming token stream into complete sentences so TTS can start
synthesizing the first sentence while LLM is still generating the rest.

Boundary markers (Vietnamese-aware):
  '. '  '! '  '? '  '\\n'
  'ạ.'  'ạ!'  'nhé.'  'nhé!'  'ạ,'  — common Vietnamese sentence endings
"""

from __future__ import annotations

import re

# Patterns that indicate a sentence boundary
_HARD_BOUNDARIES = re.compile(
    r"(?<=[.!?])\s+"           # standard: '. ' '! ' '? '
    r"|(?<=ạ\.)\s*"            # Vietnamese: 'ạ.'
    r"|(?<=ạ!)\s*"
    r"|(?<=nhé\.)\s*"
    r"|(?<=nhé!)\s*"
    r"|\n"
)

_MIN_SENTENCE_CHARS = 8  # don't emit fragments shorter than this


class SentenceSplitter:
    """Feed tokens one at a time; call .feed() to get emitted sentences.

    Example:
        splitter = SentenceSplitter()
        for token in llm_stream:
            for sentence in splitter.feed(token):
                yield sentence
        for sentence in splitter.flush():
            yield sentence
    """

    def __init__(self) -> None:
        self._buffer: str = ""

    def feed(self, token: str) -> list[str]:
        """Append token to buffer; return any completed sentences."""
        self._buffer += token
        return self._split_buffer()

    def flush(self) -> list[str]:
        """Flush remaining buffer at end of stream."""
        text = self._buffer.strip()
        self._buffer = ""
        if len(text) >= _MIN_SENTENCE_CHARS:
            return [text]
        return []

    def _split_buffer(self) -> list[str]:
        parts = _HARD_BOUNDARIES.split(self._buffer)
        if len(parts) <= 1:
            return []
        # All complete parts except the last (which may be incomplete)
        complete = parts[:-1]
        self._buffer = parts[-1]
        return [p.strip() for p in complete if len(p.strip()) >= _MIN_SENTENCE_CHARS]
