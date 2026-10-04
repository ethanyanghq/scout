"""Puts the photos and voice notes members send into words with OpenAI, so the
chat log the agent reads can hold them as text."""

import logging
import os
from pathlib import Path

import openai

from scout.media import TranscriptionError
from scout.trip import MessagePhoto

logger = logging.getLogger(__name__)

PHOTO_MODEL = "gpt-5.5"
# Describing a photo needs no reasoning, and keeps the reply fast.
PHOTO_REASONING_EFFORT = "none"
TRANSCRIPTION_MODEL = "gpt-transcribe"
DESCRIBE_PHOTO_PROMPT = (
    "Someone in a group chat planning a trip shared this photo. Describe it in "
    "a few sentences for a friend who can't see it. Copy any text in it "
    "exactly: a receipt's merchant, date, items and total, a screenshot's "
    "words, a sign or a menu. Reply with only the description."
)


class OpenAITranscriber:
    def __init__(self, client: openai.OpenAI):
        self._client = client

    def describe_photo(self, photo: MessagePhoto) -> str:
        photo_url = f"data:{photo.media_type};base64,{photo.base64_data}"
        try:
            response = self._client.chat.completions.create(
                model=PHOTO_MODEL,
                reasoning_effort=PHOTO_REASONING_EFFORT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": DESCRIBE_PHOTO_PROMPT},
                            {"type": "image_url", "image_url": {"url": photo_url}},
                        ],
                    }
                ],
            )
        except openai.OpenAIError as error:
            raise TranscriptionError(
                f"OpenAI couldn't describe a photo: {error}"
            ) from error
        return (response.choices[0].message.content or "").strip()

    def transcribe_voice_note(self, audio: Path) -> str:
        try:
            with audio.open("rb") as recording:
                transcription = self._client.audio.transcriptions.create(
                    model=TRANSCRIPTION_MODEL, file=recording
                )
        except openai.OpenAIError as error:
            raise TranscriptionError(
                f"OpenAI couldn't transcribe {audio}: {error}"
            ) from error
        return transcription.text.strip()


def connect_transcriber() -> OpenAITranscriber | None:
    if not os.environ.get("OPENAI_API_KEY"):
        logger.info(
            "Photos and voice notes won't be transcribed, since no OPENAI_API_KEY "
            "is set"
        )
        return None
    return OpenAITranscriber(openai.OpenAI())
