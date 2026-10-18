"""Run one FFmpeg compositor per active co-stream, with automatic cleanup."""

import os
import signal
import subprocess
import time
from urllib.parse import quote

from backend.core import read

RTSP = os.environ.get("MEDIA_RTSP_URL", "rtsp://mediamtx:8554")
RTMP = os.environ.get("MEDIA_RTMP_URL", "rtmp://mediamtx:1935")
processes = {}
running = True


def stop(_sig=None, _frame=None):
    global running
    running = False
    for process, _signature in processes.values():
        process.terminate()
    for process, _signature in processes.values():
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()


def command(session_id, keys, layout, audio_index=0):
    token = os.environ["MEDIA_INTERNAL_TOKEN"]
    slots = 1 if layout == "solo" else 2 if layout == "grid_2" else 4
    args = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin"]
    for key in keys:
        args += ["-rtsp_transport", "tcp", "-i", f"{RTSP}/live/{key}"]
    for _ in range(slots - len(keys)):
        args += ["-f", "lavfi", "-i", "color=c=black:s=640x360:r=25"]
    if slots == 1:
        graph = "[0:v]scale=1280:720,setsar=1[v]"
    elif slots == 2:
        graph = "[0:v]scale=640:720,setsar=1[a];[1:v]scale=640:720,setsar=1[b];[a][b]hstack=inputs=2[v]"
    elif layout == "spotlight":
        graph = ("[0:v]scale=960:720,setsar=1[a];"
                 "[1:v]scale=320:240,setsar=1[b];[2:v]scale=320:240,setsar=1[c];"
                 "[3:v]scale=320:240,setsar=1[d];[b][c][d]vstack=inputs=3[side];"
                 "[a][side]hstack=inputs=2[v]")
    else:
        graph = ";".join(f"[{i}:v]scale=640:360,setsar=1[v{i}]" for i in range(4))
        graph += ";[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|640_0|0_360|640_360[v]"
    args += ["-filter_complex", graph, "-map", "[v]"]
    if audio_index is not None:
        args += ["-map", f"{audio_index}:a?"]
    args += ["-c:v", "libx264",
             "-preset", "ultrafast", "-tune", "zerolatency", "-g", "50", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-f", "flv", f"{RTMP}/costream/{session_id}?token={quote(token, safe='')}"]
    return args


def desired(state):
    result = {}
    active = state.get("player_stream_keys", {})
    for session_id, session in state.get("costream_sessions", {}).items():
        if session["status"] != "active":
            continue
        participants = list(session["participants"])
        spotlight = session.get("spotlight")
        if session["layout"] == "spotlight" and spotlight in participants:
            participants.remove(spotlight)
            participants.insert(0, spotlight)
        keys = [active.get(pid) for pid in participants]
        if not keys or any(key is None for key in keys):
            continue
        audio_index = next((i for i, pid in enumerate(participants) if pid not in session.get("muted", [])), None)
        signature = (tuple(keys), session["layout"], audio_index)
        result[session_id] = signature
    return result


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            sessions = read(desired)
            for session_id, (process, signature) in list(processes.items()):
                if session_id not in sessions or sessions[session_id] != signature or process.poll() is not None:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    del processes[session_id]
            for session_id, signature in sessions.items():
                if session_id not in processes:
                    keys, layout, audio_index = signature
                    processes[session_id] = (subprocess.Popen(command(session_id, keys, layout, audio_index)), signature)
        except Exception as exc:
            print(f"compositor retry: {exc}", flush=True)
        time.sleep(0.25)
    stop()


if __name__ == "__main__":
    main()
