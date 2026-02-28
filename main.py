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
    audio_template = os.path.join(temp_dir, "audio.%(ext)s")

    try:
        download_audio(data.video_url, audio_template)

        actual_file = None
        for file in os.listdir(temp_dir):
            if file.endswith((".mp3", ".m4a", ".webm")):
                actual_file = os.path.join(temp_dir, file)
                break

        if not actual_file:
            raise Exception("Audio download failed")

        uploaded_file = client.files.upload(file=actual_file)

        while uploaded_file.state.name != "ACTIVE":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        prompt = f"""
        Find the FIRST exact time the topic is spoken.

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

        if not timestamp:
            raise Exception("Gemini returned empty timestamp")

        return {
            "timestamp": timestamp,
            "video_url": data.video_url,
            "topic": data.topic
        }

    except Exception as e:
        # TEMPORARY DEBUG RESPONSE
        return {
            "timestamp": "00:00:01",
            "error": str(e)
        }

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)