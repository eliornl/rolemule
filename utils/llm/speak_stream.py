"""Progressive extractor for the JSON ``speak`` string while an LLM streams."""

from __future__ import annotations

from typing import Optional, Tuple


class SpeakFieldStreamer:
    """
    Accumulate streamed JSON text and emit newly completed characters from
    the ``"speak"`` string value.

    Tolerates markdown fences, leading whitespace, and JSON escapes.
    """

    __slots__ = ("_buf", "_speak", "_emitted", "_in_speak", "_escape", "_done")

    def __init__(self) -> None:
        self._buf = ""
        self._speak = ""
        self._emitted = 0
        self._in_speak = False
        self._escape = False
        self._done = False

    @property
    def speak(self) -> str:
        """Current speak prefix (may be incomplete)."""
        return self._speak

    def feed(self, chunk: str) -> str:
        """
        Append a stream chunk and return any newly completed speak characters.

        Args:
            chunk: Next raw text delta from the model

        Returns:
            Delta to broadcast (may be empty)
        """
        if not chunk or self._done:
            return ""
        self._buf += chunk
        if not self._in_speak:
            self._try_enter_speak()
        if self._in_speak and not self._done:
            self._consume_speak_chars()
        if self._emitted >= len(self._speak):
            return ""
        delta = self._speak[self._emitted :]
        self._emitted = len(self._speak)
        return delta

    def _try_enter_speak(self) -> None:
        """Locate the opening quote of the speak value in the buffer."""
        lower = self._buf.lower()
        # Prefer "speak" then optional whitespace/colon
        key = '"speak"'
        idx = lower.find(key)
        if idx < 0:
            # Still waiting for key; keep a short tail for partial matches
            if len(self._buf) > 64:
                self._buf = self._buf[-64:]
            return
        rest = self._buf[idx + len(key) :]
        # Skip whitespace and colon
        i = 0
        while i < len(rest) and rest[i] in " \t\r\n":
            i += 1
        if i >= len(rest) or rest[i] != ":":
            return
        i += 1
        while i < len(rest) and rest[i] in " \t\r\n":
            i += 1
        if i >= len(rest) or rest[i] != '"':
            return
        # Enter speak value; retain only the unconsumed value chars
        self._in_speak = True
        self._buf = rest[i + 1 :]
        self._escape = False

    def _consume_speak_chars(self) -> None:
        """Parse speak string chars from ``_buf`` until closing quote."""
        out: list[str] = []
        i = 0
        buf = self._buf
        while i < len(buf):
            ch = buf[i]
            if self._escape:
                if ch == "u":
                    # Incomplete \uXXXX — wait for more stream chunks
                    if i + 4 >= len(buf):
                        self._speak += "".join(out)
                        self._buf = "\\" + buf[i:]
                        self._escape = False
                        return
                    hex_part = buf[i + 1 : i + 5]
                    try:
                        out.append(chr(int(hex_part, 16)))
                        i += 5
                    except ValueError:
                        out.append(ch)
                        i += 1
                    self._escape = False
                    continue
                mapped = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }.get(ch)
                if mapped is not None:
                    out.append(mapped)
                else:
                    out.append(ch)
                self._escape = False
                i += 1
                continue
            if ch == "\\":
                # Trailing backslash at end of chunk — wait for the escape target
                if i + 1 >= len(buf):
                    self._speak += "".join(out)
                    self._buf = buf[i:]
                    return
                self._escape = True
                i += 1
                continue
            if ch == '"':
                self._done = True
                i += 1
                break
            out.append(ch)
            i += 1
        self._speak += "".join(out)
        self._buf = buf[i:]


def extract_speak_delta(streamer: SpeakFieldStreamer, chunk: str) -> Tuple[str, Optional[str]]:
    """
    Feed ``chunk`` into ``streamer``.

    Returns:
        (delta, current_speak_or_None)
    """
    delta = streamer.feed(chunk)
    return delta, streamer.speak or None
