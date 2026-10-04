"""Keeps the photos and voice notes members send: each file exactly as it
arrived, a copy the AI services can read, and what's in it in words.

Files live in a folder per chat. The chat log holds only the words, so a
photo costs nothing on later turns unless the AI asks to see it again.
"""

import base64
import logging
import mimetypes
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from scout.trip import MediaKind, MessagePhoto, SharedMedia

logger = logging.getLogger(__name__)

# Claude reads images up to about this many pixels on the long side; bigger
# photos only cost more to send.
MAX_PHOTO_EDGE_PIXELS = 1568
# The audio types OpenAI transcribes, by their file extension. Anything else,
# like the CAF files iPhone voice memos arrive as, becomes m4a first.
TRANSCRIBABLE_AUDIO_EXTENSIONS = {
    "audio/flac": ".flac",
    "audio/m4a": ".m4a",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-m4a": ".m4a",
    "audio/x-wav": ".wav",
}
MEDIA_ID_LENGTH = 8


@dataclass(frozen=True)
class Attachment:
    """A file a member sent, as it arrived."""

    media_type: str
    data: bytes


class Transcriber(Protocol):
    def describe_photo(self, photo: MessagePhoto) -> str: ...

    def transcribe_voice_note(self, audio: Path) -> str: ...


class TranscriptionError(Exception):
    """The transcription service couldn't put a photo or voice note into words."""


class MediaConversionError(Exception):
    """A file couldn't be turned into a copy the AI services can read."""


class MediaLibrary:
    def __init__(self, folder: Path, transcriber: Transcriber | None):
        self._folder = folder
        # None when no transcription service is set up: files are still kept,
        # and the chat log says they couldn't be transcribed.
        self._transcriber = transcriber

    def keep(self, space_id: str, attachment: Attachment) -> SharedMedia:
        """Saves the file as sent plus a readable copy, and puts it into words."""
        kind = _kind_of(attachment.media_type)
        media_id = uuid.uuid4().hex[:MEDIA_ID_LENGTH]
        chat_folder = self._chat_folder(space_id)
        chat_folder.mkdir(parents=True, exist_ok=True)
        original = chat_folder / f"{media_id}{_extension(attachment.media_type)}"
        original.write_bytes(attachment.data)

        if kind is MediaKind.PHOTO:
            readable = chat_folder / f"{media_id}.readable.jpg"
            _convert_to_jpeg(original, readable)
            transcript = self._put_into_words(
                kind, lambda words: words.describe_photo(load_photo(readable))
            )
        else:
            readable = _transcribable_audio(original, attachment.media_type)
            transcript = self._put_into_words(
                kind, lambda words: words.transcribe_voice_note(readable)
            )
        return SharedMedia(media_id, kind, original, readable, transcript)

    def delete_chat(self, space_id: str) -> None:
        """Deletes every file the chat sent, as resetting its trip should."""
        chat_folder = self._chat_folder(space_id)
        if chat_folder.exists():
            shutil.rmtree(chat_folder)

    def _chat_folder(self, space_id: str) -> Path:
        # Chat IDs come from the messaging provider, so keep only path-safe
        # letters.
        return self._folder / re.sub(r"[^\w-]", "_", space_id)

    def _put_into_words(self, kind: MediaKind, transcribe) -> str | None:
        if self._transcriber is None:
            return None
        try:
            return transcribe(self._transcriber)
        except TranscriptionError:
            # The message still reaches the chat; its log line says the
            # transcription failed, and this says why.
            logger.exception("Couldn't put a %s into words", kind)
            return None


def load_photo(readable_path: Path) -> MessagePhoto:
    """A kept photo's readable copy, ready to show the AI."""
    jpeg = readable_path.read_bytes()
    return MessagePhoto("image/jpeg", base64.b64encode(jpeg).decode("ascii"))


def _kind_of(media_type: str) -> MediaKind:
    if media_type.startswith("image/"):
        return MediaKind.PHOTO
    if media_type.startswith("audio/"):
        return MediaKind.VOICE_NOTE
    raise MediaConversionError(f"scout keeps photos and voice notes, not {media_type}")


def _extension(media_type: str) -> str:
    """The usual extension for a type, like .jpg, or one made from its name
    (image/heic → .heic, audio/x-caf → .caf) when Python doesn't know it."""
    known = TRANSCRIBABLE_AUDIO_EXTENSIONS.get(media_type)
    known = known or mimetypes.guess_extension(media_type)
    subtype = media_type.split("/")[-1].removeprefix("x-")
    return known or f".{subtype}"


def _convert_to_jpeg(photo: Path, jpeg: Path) -> None:
    # iPhones send HEIC, which the AI can't read, so every photo becomes a
    # downsized JPEG through macOS's built-in sips.
    edge = str(MAX_PHOTO_EDGE_PIXELS)
    _run_converter(
        "sips", ["-s", "format", "jpeg", "-Z", edge, str(photo), "--out", str(jpeg)]
    )


def _transcribable_audio(voice_note: Path, media_type: str) -> Path:
    if media_type in TRANSCRIBABLE_AUDIO_EXTENSIONS:
        return voice_note
    m4a = voice_note.with_suffix(".readable.m4a")
    # macOS's built-in afconvert reads iPhone voice memos (Opus in CAF).
    _run_converter("afconvert", ["-f", "m4af", "-d", "aac", str(voice_note), str(m4a)])
    return m4a


def _run_converter(tool: str, arguments: list[str]) -> None:
    if shutil.which(tool) is None:
        raise MediaConversionError(
            f"Photos and voice notes need macOS's {tool}, so they only work on a Mac."
        )
    result = subprocess.run([tool, *arguments], capture_output=True, text=True)
    if result.returncode != 0:
        raise MediaConversionError(
            f"{tool} {' '.join(arguments)} failed: {result.stderr.strip()}"
        )
