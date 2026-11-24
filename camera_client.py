import base64
import os
import subprocess
import sys
import threading

import cv2
import requests

from config import OLLAMA_URL


VISION_MODEL = os.environ.get(
    "NICO_VISION_MODEL",
    "qwen2.5vl:3b",
)
CAMERA_INDEX = int(os.environ.get("NICO_CAMERA_INDEX", "0"))

_speech_lock = threading.Lock()
_speech_process = None


def analyze_camera():
    """Capture one image and ask the local Ollama vision model about it."""
    camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(CAMERA_INDEX)

    try:
        if not camera.isOpened():
            return (
                "I couldn't open the camera. Check Windows camera "
                "permissions and close other apps that may be using it."
            )

        frame = None
        for _ in range(5):
            success, current_frame = camera.read()
            if success:
                frame = current_frame

        if frame is None:
            return "The camera opened, but no image could be captured."

        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 80],
        )
        if not success:
            return "I couldn't encode the camera image."

        image_data = base64.b64encode(
            encoded.tobytes()
        ).decode("ascii")

    finally:
        camera.release()

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": VISION_MODEL,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Describe clearly visible details in this image. "
                            "Do not identify the person. If describing facial "
                            "expression, explain that an image cannot reveal "
                            "someone's true emotion with certainty."
                        ),
                        "images": [image_data],
                    }
                ],
            },
            timeout=(5, 120),
        )
        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})
        answer = (
            message.get("content", "").strip()
            if isinstance(message, dict)
            else ""
        )
        return answer or "The vision model returned an empty response."

    except requests.exceptions.ConnectionError:
        return "I can't connect to Ollama. Start Ollama and try again."
    except requests.exceptions.Timeout:
        return "Camera analysis took too long. Please try again."
    except requests.exceptions.HTTPError as error:
        status = getattr(error.response, "status_code", "unknown")
        return (
            f"Ollama returned HTTP {status}. Install the vision model with "
            f"`ollama pull {VISION_MODEL}`."
        )
    except (requests.RequestException, ValueError) as error:
        return f"Camera analysis failed: {error}"
    except Exception as error:
        return f"Unexpected camera analysis error: {error}"


def stop_speaking():
    """Immediately stop any speech process started by NICO."""
    global _speech_process

    with _speech_lock:
        process = _speech_process
        _speech_process = None

    if process is not None and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
        except OSError:
            pass


def speak_text(text, cancel_event=None):
    """Speak using a suitable installed Windows voice; supports cancellation."""
    global _speech_process

    if sys.platform != "win32":
        return False

    text = str(text).strip()
    if not text or (cancel_event and cancel_event.is_set()):
        return False

    text_encoded = base64.b64encode(
        text.encode("utf-8")
    ).decode("ascii")

    # Prefer installed female voices for South African, Kenyan, Nigerian,
    # Ghanaian, or Zimbabwean English. Fall back to any installed female
    # English voice, then let Windows use its default voice.
    script = f"""
Add-Type -AssemblyName System.Speech

$textBytes = [System.Convert]::FromBase64String('{text_encoded}')
$text = [System.Text.Encoding]::UTF8.GetString($textBytes)

$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Rate = 0
$speaker.Volume = 100

$preferredCultures = @('en-ZA', 'en-KE', 'en-NG', 'en-GH', 'en-ZW')
$voices = @($speaker.GetInstalledVoices() |
    Where-Object {{ $_.Enabled }} |
    ForEach-Object {{ $_.VoiceInfo }})

$femaleVoices = @($voices | Where-Object {{
    $_.Gender.ToString() -eq 'Female'
}})

$voice = $femaleVoices | Where-Object {{
    $preferredCultures -contains $_.Culture.Name
}} | Select-Object -First 1

if (-not $voice) {{
    $voice = $femaleVoices | Where-Object {{
        $_.Culture.Name -like 'en-*'
    }} | Select-Object -First 1
}}

if ($voice) {{
    $speaker.SelectVoice($voice.Name)
}}

$speaker.Speak($text)
$speaker.Dispose()
"""

    encoded_command = base64.b64encode(
        script.encode("utf-16le")
    ).decode("ascii")

    process = None

    try:
        with _speech_lock:
            if cancel_event and cancel_event.is_set():
                return False

            # Stop an earlier speech process before starting this one.
            old_process = _speech_process
            if old_process is not None and old_process.poll() is None:
                try:
                    old_process.terminate()
                except OSError:
                    pass

            process = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded_command,
                ],
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _speech_process = process

        while process.poll() is None:
            if cancel_event and cancel_event.is_set():
                stop_speaking()
                return False
            cancel_event.wait(0.1) if cancel_event else threading.Event().wait(0.1)

        return process.returncode == 0

    except (OSError, subprocess.SubprocessError):
        return False

    finally:
        with _speech_lock:
            if _speech_process is process:
                _speech_process = None