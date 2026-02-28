import os
import time
import tempfile
import shutil
import yt_dlp

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class AskRequest(BaseModel):
    video_url: str
    topic: str


class TimestampResponse(BaseModel):
    timestamp: str


def download_audio(url: str, output_path: str):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "quiet": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


@app.post("/ask")
def ask(data: AskRequest):

    temp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(temp_dir, "audio.%(ext)s")

    try:
        # 1️⃣ Download full audio
        download_audio(data.video_url, audio_path)

        # Find actual downloaded file
        actual_file = None
        for file in os.listdir(temp_dir):
            if file.endswith((".mp3", ".m4a", ".webm")):
                actual_file = os.path.join(temp_dir, file)
                break

        if not actual_file:
            return {
                "timestamp": "00:00:00",
                "video_url": data.video_url,
                "topic": data.topic
            }

        # 2️⃣ Upload to Gemini Files API
        uploaded_file = client.files.upload(file=actual_file)

        # 3️⃣ Wait until ACTIVE
        while uploaded_file.state.name != "ACTIVE":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        # 4️⃣ Ask Gemini for exact first mention timestamp
        prompt = f"""
        Find the FIRST time the following topic is spoken in the audio.

        Topic: {data.topic}

        Return ONLY the timestamp in HH:MM:SS format.
        """

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[uploaded_file, prompt],
            config={
                "response_schema": TimestampResponse,
                "response_mime_type": "application/json"
            }
        )

        timestamp = response.parsed.timestamp

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
        shutil.rmtree(temp_dir, ignore_errors=True)