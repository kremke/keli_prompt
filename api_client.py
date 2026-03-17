"""Google Gemini TTS API client for Keli Prompt."""

import base64
from typing import List

# The Gemini TTS API does not expose a voices-listing endpoint.
# This is the complete set of available prebuilt voices as documented by Google.
KNOWN_VOICES: List[str] = sorted([
    "Aoede", "Charon", "Fenrir", "Kore", "Puck",
    "Achird", "Algieba", "Alnilam", "Aoede", "Auva",
    "Callirrhoe", "Despina", "Enceladus", "Erinome",
    "Gacrux", "Iocaste", "Kore", "Laomedeia", "Leda",
    "Orus", "Puck", "Pulcherrima", "Rasalgethi", "Sadachbia",
    "Sadaltager", "Schedar", "Sulafat", "Umbriel", "Vindemiatrix",
    "Zephyr", "Zubenelgenubi",
])
# Remove duplicates that crept in above
KNOWN_VOICES = sorted(set(KNOWN_VOICES))

TTS_MODEL = "gemini-2.5-flash-preview-tts"

# PCM audio format returned by the Gemini TTS API
PCM_SAMPLE_RATE = 24000
PCM_SAMPLE_WIDTH = 2   # bytes (16-bit signed little-endian)
PCM_CHANNELS = 1


def _decode_audio(data) -> bytes:
    """Return raw bytes regardless of whether the SDK returned bytes or a base64 string."""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return base64.b64decode(data)
    raise TypeError(f"Unexpected audio data type: {type(data)}")


def refresh_voices(api_key: str) -> List[str]:
    """
    Verify the API key is usable and return the list of available TTS voices.

    Because the Gemini API has no voice-listing endpoint we validate the key
    by listing models, then return the known voice catalogue.
    """
    from google import genai  # type: ignore

    client = genai.Client(api_key=api_key)
    # A lightweight call — list models — to confirm the key works.
    # If this raises, the caller handles the exception.
    list(client.models.list())
    return KNOWN_VOICES


def generate_audio_single(
    api_key: str,
    prompt: str,
    voice: str,
) -> bytes:
    """Generate TTS audio for single-speaker mode.  Returns raw PCM bytes."""
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice,
                    )
                )
            ),
        ),
    )
    raw = response.candidates[0].content.parts[0].inline_data.data
    return _decode_audio(raw)


def generate_audio_dual(
    api_key: str,
    prompt: str,
    speaker1_label: str,
    speaker1_voice: str,
    speaker2_label: str,
    speaker2_voice: str,
) -> bytes:
    """Generate TTS audio for dual-speaker mode.  Returns raw PCM bytes."""
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        types.SpeakerVoiceConfig(
                            speaker=speaker1_label,
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=speaker1_voice,
                                )
                            ),
                        ),
                        types.SpeakerVoiceConfig(
                            speaker=speaker2_label,
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=speaker2_voice,
                                )
                            ),
                        ),
                    ]
                )
            ),
        ),
    )
    raw = response.candidates[0].content.parts[0].inline_data.data
    return _decode_audio(raw)
