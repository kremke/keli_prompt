"""Audio assembly and export utilities for Keli Prompt."""

import io
import os
import tempfile
import wave
from typing import List

from api_client import PCM_SAMPLE_RATE, PCM_SAMPLE_WIDTH, PCM_CHANNELS


# ---------------------------------------------------------------------------
# WAV helpers (no external dependencies)
# ---------------------------------------------------------------------------

def pcm_to_wav_bytes(pcm_data: bytes) -> bytes:
    """Wrap raw PCM bytes in a WAV container and return the result as bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(PCM_CHANNELS)
        wf.setsampwidth(PCM_SAMPLE_WIDTH)
        wf.setframerate(PCM_SAMPLE_RATE)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def play_pcm_audio(pcm_data: bytes) -> None:
    """
    Play raw PCM audio synchronously via a temporary WAV file.

    Uses the standard-library ``winsound`` module (Windows only).
    Call this from a worker thread to avoid blocking the UI.
    """
    import winsound  # type: ignore  (Windows-only)

    wav_bytes = pcm_to_wav_bytes(pcm_data)
    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(wav_bytes)
        winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# MP3 export (requires pydub + ffmpeg)
# ---------------------------------------------------------------------------

def _make_segment(pcm_data: bytes):
    """Create a pydub AudioSegment from raw PCM bytes."""
    from pydub import AudioSegment  # type: ignore

    return AudioSegment(
        data=pcm_data,
        sample_width=PCM_SAMPLE_WIDTH,
        frame_rate=PCM_SAMPLE_RATE,
        channels=PCM_CHANNELS,
    )


def export_chunk_mp3(pcm_data: bytes, path: str) -> None:
    """Export a single PCM chunk as an MP3 file."""
    seg = _make_segment(pcm_data)
    seg.export(path, format="mp3")


def combine_and_export_mp3(
    pcm_chunks: List[bytes],
    output_path: str,
    chunk_base_path: str | None = None,
    save_chunks: bool = False,
) -> None:
    """
    Combine all PCM chunks and export as a single MP3.

    If *save_chunks* is True and *chunk_base_path* is provided, each chunk is
    also saved individually as ``<chunk_base_path>_01.mp3``, ``_02.mp3``, etc.
    """
    if not pcm_chunks:
        raise ValueError("No audio chunks to combine.")

    from pydub import AudioSegment  # type: ignore

    segments = []
    for i, pcm in enumerate(pcm_chunks):
        seg = _make_segment(pcm)
        segments.append(seg)
        if save_chunks and chunk_base_path:
            chunk_path = f"{chunk_base_path}_{i + 1:02d}.mp3"
            seg.export(chunk_path, format="mp3")

    combined: AudioSegment = segments[0]
    for seg in segments[1:]:
        combined = combined + seg  # type: ignore[operator]

    combined.export(output_path, format="mp3")
