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
# The chat log keeps only this description, and the agent splits costs and
# plans from it, so anything with numbers or details is copied in full.
DESCRIBE_PHOTO_PROMPT = """\
Someone in a group chat planning a trip shared this photo. The trip planner \
reading the chat only gets your description, not the photo, so write down \
everything it might need.

Start with one line saying what the photo is.

For a receipt, bill or invoice, copy it completely: the merchant and its \
address, the date and time, every line item with its quantity and price, the \
subtotal, each tax, fee and service charge, the tip, the final total, the \
currency, and how it was paid (card brand and last four digits, if shown). \
Say which number is the final amount paid. If something is cut off, blurry or \
handwritten, say so rather than guessing.

For a screenshot or anything with text (a booking or flight confirmation, a \
listing, a ticket, a menu, a map, a message), copy all of its text and \
numbers exactly: names, dates, times, prices, addresses, confirmation codes, \
flight numbers.

For a plain photo (a place, people, a view), describe it in a few sentences.

Reply with only the description, as plain text with no markdown."""


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
