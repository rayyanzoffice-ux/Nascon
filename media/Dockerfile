FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY media/requirements.txt /app/media/requirements.txt
RUN pip install --no-cache-dir -r /app/media/requirements.txt
COPY backend/ /app/backend/
COPY media/ /app/media/
CMD ["python", "-m", "media.compositor"]
