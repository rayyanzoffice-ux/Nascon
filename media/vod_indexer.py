"""Upload closed MediaMTX fMP4 segments to MinIO and index them."""

import hashlib
import os
from pathlib import Path
import time

from backend.core import mutate, read

ROOT = Path(os.environ.get("MEDIA_RECORDINGS_ROOT", "/recordings"))
BUCKET = os.environ.get("VOD_BUCKET", "nascon-vod")


def index_record(state, path, object_key, size):
    parts = Path(path).parts
    media_path = "/".join(parts[:2])
    player_id = None
    if len(parts) >= 2 and parts[0] == "live":
        player_id = state.get("stream_keys", {}).get(parts[1], {}).get("player_id")
    elif len(parts) >= 2 and parts[0] == "costream":
        player_id = state.get("costream_sessions", {}).get(parts[1], {}).get("host")
    vod_id = hashlib.sha256(object_key.encode("utf-8")).hexdigest()[:24]
    record = {"vod_id": vod_id, "player_id": player_id, "media_path": media_path,
              "object_key": object_key, "size_bytes": size,
              "playback_url": f"http://localhost:9000/{BUCKET}/{object_key}",
              "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    state.setdefault("vod_index", {}).setdefault(vod_id, record)
    return record


def main():
    import boto3
    import botocore.exceptions

    endpoint = os.environ.get("MINIO_URL", "http://minio:9000")
    s3 = boto3.client("s3", endpoint_url=endpoint,
                      aws_access_key_id=os.environ["MINIO_ROOT_USER"],
                      aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"])
    while True:
        try:
            try:
                s3.head_bucket(Bucket=BUCKET)
            except botocore.exceptions.ClientError:
                s3.create_bucket(Bucket=BUCKET)
            s3.put_bucket_policy(Bucket=BUCKET, Policy=(
                '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
                '"Principal":"*","Action":["s3:GetObject"],'
                '"Resource":["arn:aws:s3:::' + BUCKET + '/*"]}]}'))
            for file in ROOT.rglob("*.mp4"):
                if time.time() - file.stat().st_mtime < 0.5:
                    continue
                relative = file.relative_to(ROOT).as_posix()
                vod_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
                if read(lambda state: vod_id in state.get("vod_index", {})):
                    continue
                s3.upload_file(str(file), BUCKET, relative, ExtraArgs={"ContentType": "video/mp4"})
                mutate(lambda state: index_record(state, relative, relative, file.stat().st_size))
        except Exception as exc:
            print(f"VOD indexing retry: {exc}", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
