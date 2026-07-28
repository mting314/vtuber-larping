from app.ingestion import parse_youtube_atom_feed

SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <yt:videoId>Nd9rzBUcOHA</yt:videoId>
    <yt:channelId>UC1uv2Oq6kNxgATlCiez59zQ</yt:channelId>
    <title>Peeking Respectfully While Slobbering in the Hot Springs Zatsudan</title>
    <published>2026-07-27T00:00:00+00:00</published>
    <author>
      <name>Shiori Novella</name>
    </author>
  </entry>
</feed>
"""

def test_parse_atom_feed():
    entries = parse_youtube_atom_feed(SAMPLE_ATOM_XML)
    assert len(entries) == 1
    assert entries[0]["video_id"] == "Nd9rzBUcOHA"
    assert entries[0]["channel_name"] == "Shiori Novella"
