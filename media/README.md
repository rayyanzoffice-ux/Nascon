# Day 2 streaming integration

The isolated feature branch starts the API through `backend.streaming_main:app` so its three routers are available without editing Chat 01's `backend/main.py`. After the integration branch includes those routers in `backend/main.py`, the wrapper checks for existing routes and avoids duplicates.

## Compose handoff for Chat 07

Merge `media/docker-compose.streaming.yml` with the main Compose file. It adds:

| Service | Purpose | Host ports |
| --- | --- | --- |
| `mediamtx` | RTMP ingest, HLS playback, WebRTC WHIP/WHEP, recording, control API | 1935 TCP, 8888 TCP, 8889 TCP, 8189 UDP |
| `media_compositor` | FFmpeg split-screen publication to the stable `costream/{session_id}` path | internal only |
| `vod_indexer` | Uploads finished fMP4 recording segments to MinIO and updates the VOD index | internal only |
| `minio` extension | Browser-accessible VOD objects | 9000 TCP |
| `api` extension | Day 2 salt, MediaMTX control endpoint, internal publisher credential, streaming entry point | existing 8080 TCP |

Provide `DAY2_SALT` and an independent random `MEDIA_INTERNAL_TOKEN` through the environment. Keep both out of Git. The main Compose definition already supplies PostgreSQL and MinIO credentials to its own services; update the `vod_indexer` environment if those values change. The record volume is shared by MediaMTX and the indexer.

For standalone verification from the repository root:

```sh
docker compose -f docker-compose.yml -f media/docker-compose.streaming.yml up -d --build
```

Generate a player key through `POST /audit/v1/stream/key`. Publish with OBS to `rtmp://localhost:1935/live/<key>`, or with WHIP to `http://localhost:8889/live/<key>/whip`. Read HLS from `http://localhost:8888/live/<key>/index.m3u8`; WebRTC WHEP uses the same path at port 8889 with `/whep`. Rotation or revocation invalidates database authorization and calls the MediaMTX control API to disconnect an existing publisher.

Co-stream composition starts when every active participant has an active key and a readable media path. The FFmpeg worker reconstructs the composite when the participant list, layout, mute state, spotlight, or keys change. A host disconnect keeps the `costream/{session_id}` path and `chat-{session_id}` room stable, then promotes the first remaining participant.

Recording uses MediaMTX fMP4 segments. The indexer scans completed segments, uploads each once to `nascon-vod` in MinIO, and records it in `vod_index` for the athlete profile.

The current Windows environment does not permit connecting to Docker Desktop, so full RTMP/HLS/WHIP and MinIO operation must be checked on the integration host. `docker compose ... config --quiet` passes locally.
