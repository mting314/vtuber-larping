from app.transcriber import parse_vtt, chunk_cues

SAMPLE_VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:05.000
Hello everyone welcome to the hot spring.

00:00:05.000 --> 00:00:10.000
Please remove all your clothing right now.
"""

def test_parse_vtt():
    cues = parse_vtt(SAMPLE_VTT)
    assert len(cues) == 2
    assert "hot spring" in cues[0].text
    assert cues[1].start_sec == 5

def test_chunk_cues():
    cues = parse_vtt(SAMPLE_VTT)
    chunks = chunk_cues(cues, interval_minutes=15)
    assert len(chunks) == 1
    assert chunks[0]["start_time"] == "00:00:01"
