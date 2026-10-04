"""Keeping the photos and voice notes members send, with OpenAI's transcription
replaced by a stand-in. The conversions run macOS's own tools for real."""

import shutil
from pathlib import Path

import pytest

from scout.media import (
    Attachment,
    MediaLibrary,
    TranscriptionError,
    load_photo,
)
from scout.trip import MediaKind

FIXTURES = Path(__file__).parent / "fixtures"
IPHONE_PHOTO = Attachment("image/heic", (FIXTURES / "photo.heic").read_bytes())
IPHONE_VOICE_MEMO = Attachment(
    "audio/x-caf", (FIXTURES / "voice-memo.caf").read_bytes()
)
SPACE = "group-chat-1"

needs_a_mac = pytest.mark.skipif(
    shutil.which("sips") is None or shutil.which("afconvert") is None,
    reason="converting photos and voice notes needs macOS's sips and afconvert",
)


class FakeTranscriber:
    """Stands in for OpenAI: describes every photo and transcribes every voice
    note the same way, and keeps what it was given."""

    def __init__(self):
        self.photos_described = []
        self.voice_notes_heard = []

    def describe_photo(self, photo):
        self.photos_described.append(photo)
        return "A receipt from Casa Brisa, total $164.00"

    def transcribe_voice_note(self, audio):
        self.voice_notes_heard.append(audio)
        return "I'm flying from Boston."


class BrokenTranscriber:
    def describe_photo(self, photo):
        raise TranscriptionError("OpenAI is unreachable")

    def transcribe_voice_note(self, audio):
        raise TranscriptionError("OpenAI is unreachable")


@needs_a_mac
def test_describes_a_jpeg_copy_of_an_iphone_photo(tmp_path):
    transcriber = FakeTranscriber()
    library = MediaLibrary(tmp_path, transcriber)

    photo = library.keep(SPACE, IPHONE_PHOTO)

    assert photo.transcript == "A receipt from Casa Brisa, total $164.00"
    [described] = transcriber.photos_described
    assert described == load_photo(photo.readable_path)
    assert photo.readable_path.read_bytes().startswith(b"\xff\xd8")  # JPEG


@needs_a_mac
def test_transcribes_an_iphone_voice_memo_as_m4a(tmp_path):
    transcriber = FakeTranscriber()
    library = MediaLibrary(tmp_path, transcriber)

    voice_note = library.keep(SPACE, IPHONE_VOICE_MEMO)

    assert voice_note.kind is MediaKind.VOICE_NOTE
    assert voice_note.original_path.suffix == ".caf"
    assert voice_note.original_path.read_bytes() == IPHONE_VOICE_MEMO.data
    assert transcriber.voice_notes_heard == [voice_note.readable_path]
    assert voice_note.readable_path.suffix == ".m4a"
    assert voice_note.transcript == "I'm flying from Boston."


def test_keeps_media_without_words_when_transcription_fails(tmp_path):
    library = MediaLibrary(tmp_path, BrokenTranscriber())

    voice_note = library.keep(SPACE, Attachment("audio/mpeg", b"mp3 bytes"))

    assert voice_note.transcript is None
    assert voice_note.original_path.exists()


def test_keeps_each_chat_in_a_path_safe_folder_of_its_own(tmp_path):
    library = MediaLibrary(tmp_path, FakeTranscriber())

    voice_note = library.keep("../chat/1", Attachment("audio/mpeg", b"mp3 bytes"))

    assert voice_note.original_path.parent == tmp_path / "___chat_1"
