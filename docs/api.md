# 🔌 REST API Specification

The FastAPI application provides a RESTful interface for searching streams, managing user settings, and triggering manual stream summaries.

---

## 📡 Endpoints

### 1. List Streams
`GET /api/streams`

**Query Parameters:**
* `agency` *(optional)*: Filter by agency (e.g. `Hololive English`, `Hololive ID`, `VShojo`).
* `vtuber_id` *(optional)*: Filter by VTuber ID.
* `q` *(optional)*: Search query string.

**Response:**
```json
[
  {
    "id": 1,
    "video_id": "VMfR5nr8gic",
    "title": "【Just Chatting】I'M FREE CELEBRATE",
    "duration_seconds": 7200,
    "published_at": "2026-07-27T18:00:00Z",
    "thumbnail_url": "https://i.ytimg.com/vi/VMfR5nr8gic/hqdefault.jpg",
    "status": "COMPLETED",
    "error_message": null,
    "warning_message": null,
    "vtuber": {
      "id": 1,
      "name": "Shiori Novella",
      "agency": "Hololive English"
    },
    "has_summary": true
  }
]
```

---

### 2. Get Stream Details & Summary
`GET /api/streams/{stream_id}`

**Response:**
```json
{
  "id": 1,
  "video_id": "VMfR5nr8gic",
  "title": "【Just Chatting】I'M FREE CELEBRATE",
  "status": "COMPLETED",
  "summary": {
    "master_summary": "# 【Just Chatting】I'M FREE CELEBRATE\n\n## ⚡ Quick Stream Highlights (TL;DR)\n...",
    "standout_highlights": [
      {
        "timestamp": "00:15:30",
        "title": "Hot Springs Anecdote",
        "description": "Shiori discussed her trip to the hot springs."
      }
    ]
  }
}
```

---

### 3. Trigger Manual Stream Summarization
`POST /api/streams/trigger`

**Request Body:**
```json
{
  "url": "https://www.youtube.com/watch?v=VMfR5nr8gic"
}
```

**Response:**
```json
{
  "message": "Stream summary job queued",
  "stream_id": 1,
  "video_id": "VMfR5nr8gic"
}
```

---

### 4. Get / Update User Settings
`GET /api/settings`  
`PUT /api/settings`

**Request Body (PUT):**
```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/...",
  "is_discord_enabled": true,
  "summary_style": "bullet_first"
}
```
