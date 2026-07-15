"""Unit tests for SpeakFieldStreamer progressive JSON speak extraction."""

from __future__ import annotations

from utils.llm.speak_stream import SpeakFieldStreamer


def test_speak_streamer_emits_incrementally() -> None:
    s = SpeakFieldStreamer()
    assert s.feed('{"speak": "Hel') == "Hel"
    assert s.feed("lo there") == "lo there"
    assert s.feed('", "act": "next_question"}') == ""
    assert s.speak == "Hello there"


def test_speak_streamer_handles_escapes() -> None:
    s = SpeakFieldStreamer()
    chunks = ['{"speak":"Say \\"hi\\"\\nand bye"}']
    out = "".join(s.feed(c) for c in chunks)
    assert out == 'Say "hi"\nand bye'
    assert s.speak == out


def test_speak_streamer_ignores_other_fields_first() -> None:
    s = SpeakFieldStreamer()
    delta = s.feed('{"act":"next_question","speak":"Q?"}')
    assert delta == "Q?"
    assert s.speak == "Q?"


def test_speak_streamer_markdown_fence_prefix() -> None:
    s = SpeakFieldStreamer()
    parts = ["```json\n", '{"speak": "Hi"}']
    text = "".join(s.feed(p) for p in parts)
    assert text == "Hi"


def test_speak_streamer_unicode_escape_split_across_chunks() -> None:
    s = SpeakFieldStreamer()
    # "speak":"A\u2603B"  (snowman) split mid-escape
    assert s.feed('{"speak":"A\\u') == "A"
    assert s.feed("2603") == "☃"
    assert s.feed('B"}') == "B"
    assert s.speak == "A☃B"


def test_speak_streamer_trailing_backslash_waits() -> None:
    s = SpeakFieldStreamer()
    assert s.feed('{"speak":"x\\') == "x"
    assert s.feed('n y"}') == "\n y"
    assert s.speak == "x\n y"
