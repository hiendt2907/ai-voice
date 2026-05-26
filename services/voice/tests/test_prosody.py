from tts.prosody import beats_to_chunks, PAUSE_DURATION_MS


def test_beats_to_chunks_basic():
    beats = [
        {"text": "Xin chào,", "pause_after": "breath", "role": "agent"},
        {"text": "tôi là Linh.", "pause_after": "none", "role": "agent"},
    ]
    chunks = beats_to_chunks(beats)

    assert len(chunks) == 2
    assert chunks[0].text == "Xin chào,"
    assert chunks[0].pause_after_ms == PAUSE_DURATION_MS["breath"]
    assert chunks[1].pause_after_ms == 0


def test_beats_to_chunks_defaults():
    beats = [{"text": "Hello"}]
    chunks = beats_to_chunks(beats)

    assert chunks[0].pause_after_ms == 0
    assert chunks[0].role == "agent"


def test_pause_durations_ordered():
    tiers = ["none", "micro", "short", "breath", "medium", "long", "turn"]
    durations = [PAUSE_DURATION_MS[t] for t in tiers]
    assert durations == sorted(durations), "Pause durations must be strictly non-decreasing"
