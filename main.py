import os
import re
import shutil
import tempfile
import yt_dlp

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    video_url: str
    topic: str


def download_subtitles(url: str, output_path: str):
    ydl_opts = {
        "writesubtitles": True,
        "writeautomaticsub": True,
        "skip_download": True,
        "subtitlesformat": "vtt",
        "outtmpl": output_path,
        "quiet": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def parse_vtt_for_topic(vtt_file: str, topic: str):
    topic = topic.lower()

    with open(vtt_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i in range(len(lines)):
        line = lines[i].strip().lower()

        if topic in line:
            # Timestamp is usually in previous line
            timestamp_line = lines[i - 1].strip()

            match = re.match(r"(\d{2}:\d{2}:\d{2})\.\d+ -->", timestamp_line)
            if match:
                return match.group(1)

    return None


@app.post("/ask")
def ask(data: AskRequest):

    temp_dir = tempfile.mkdtemp()

    try:
        output_template = os.path.join(temp_dir, "%(title)s.%(ext)s")

        # 1️⃣ Download subtitles
        download_subtitles(data.video_url, output_template)

        # 2️⃣ Find VTT file
        vtt_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(".vtt"):
                vtt_file = os.path.join(temp_dir, file)
                break

        if not vtt_file:
            raise HTTPException(status_code=404, detail="Subtitles not found for this video")

        # 3️⃣ Search topic
        timestamp = parse_vtt_for_topic(vtt_file, data.topic)

        if not timestamp:
            raise HTTPException(status_code=404, detail="Topic not found in subtitles")

        return {
            "timestamp": timestamp,
            "video_url": data.video_url,
            "topic": data.topic
        }

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)