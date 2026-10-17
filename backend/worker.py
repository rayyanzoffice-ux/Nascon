import os, time
import redis

def main():
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    while True:
        try:
            r = redis.Redis.from_url(url)
            r.xgroup_create("nascon:events", "workers", id="0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        except Exception:
            time.sleep(2)
            continue
        try:
            events = r.xreadgroup("workers", "worker1", {"nascon:events": ">"}, count=10, block=3000)
            for stream, entries in events:
                for event_id, _ in entries:
                    r.xack(stream, "workers", event_id)
        except Exception:
            time.sleep(2)

if __name__ == "__main__":
    main()
