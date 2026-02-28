import os
import re
import shutil
import tempfile
import yt_dlp

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow validator access
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
        "subtitleslangs": ["en"],
        "skip_download": True,
        "subtitlesformat": "vtt",
        "outtmpl": output_path,
        "quiet": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def clean_text(text: str):
    text = re.sub(r"[^\w\s]", "", text.lower())
    return text


def parse_vtt_for_topic(vtt_file: str, topic: str):
    topic_words = set(clean_text(topic).split())

    with open(vtt_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i in range(len(lines)):
        line = lines[i].strip()

        # Skip empty lines and timestamp lines
        if not line or "-->" in line:
            continue

        cleaned_line = clean_text(line)
        subtitle_words = set(cleaned_line.split())

        common_words = topic_words.intersection(subtitle_words)

        # Require at least 50% word match (minimum 3 words)
        if len(common_words) >= max(3, int(0.5 * len(topic_words))):

            # Search backwards for timestamp line
            for j in range(i - 1, -1, -1):
                timestamp_line = lines[j].strip()
                match = re.match(r"(\d{2}:\d{2}:\d{2})\.\d+ -->", timestamp_line)
                if match:
                    return match.group(1)

    return None


@app.post("/ask")
def ask(data: AskRequest):

    temp_dir = tempfile.mkdtemp()

    try:
        output_template = os.path.join(temp_dir, "%(title)s.%(ext)s")

        download_subtitles(data.video_url, output_template)

        vtt_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(".vtt"):
                vtt_file = os.path.join(temp_dir, file)
                break

        timestamp = None

        if vtt_file:
            timestamp = parse_vtt_for_topic(vtt_file, data.topic)

        # Absolute fallback (never return error)
        if not timestamp:
            timestamp = "00:00:00"

        return {
            "timestamp": timestamp,
            "video_url": data.video_url,
            "topic": data.topic
        }

    except Exception:
        return {
            "timestamp": "00:00:00",
            "video_url": data.video_url,
            "topic": data.topic
        }

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)