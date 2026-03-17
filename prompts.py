"""Prompt templates for Keli Prompt."""

_SINGLE_TEMPLATE = (
    "Speak the following text exactly as written.\n"
    "Do not add any introduction.\n"
    "Do not add any explanation.\n"
    "Do not add any commentary.\n"
    "Do not summarize.\n"
    "Do not change the wording.\n"
    "Only speak the text provided.\n"
    "\n"
    "Text:\n"
    "{chunk}"
)

_DUAL_TEMPLATE = (
    "Speak the following dialogue exactly as written.\n"
    "There are two speakers.\n"
    'Lines beginning with "{speaker1_label}:" belong to the first speaker.\n'
    'Lines beginning with "{speaker2_label}:" belong to the second speaker.\n'
    "Do not speak the speaker labels aloud.\n"
    "Do not add any introduction.\n"
    "Do not add any explanation.\n"
    "Do not add any commentary.\n"
    "Do not summarize.\n"
    "Do not change the wording.\n"
    "Only speak the dialogue text provided.\n"
    "\n"
    "Dialogue:\n"
    "{chunk}"
)

_VOICE_TEST_TEXT = "This is a voice preview."


def build_single_prompt(chunk: str) -> str:
    return _SINGLE_TEMPLATE.format(chunk=chunk)


def build_dual_prompt(chunk: str, speaker1_label: str, speaker2_label: str) -> str:
    return _DUAL_TEMPLATE.format(
        chunk=chunk,
        speaker1_label=speaker1_label,
        speaker2_label=speaker2_label,
    )


def build_voice_test_prompt_single() -> str:
    return _SINGLE_TEMPLATE.format(chunk=_VOICE_TEST_TEXT)


def build_voice_test_prompt_dual(speaker_label: str) -> str:
    """Test prompt for one speaker in dual mode — uses only that speaker's label."""
    chunk = f"{speaker_label}: {_VOICE_TEST_TEXT}"
    return _DUAL_TEMPLATE.format(
        chunk=chunk,
        speaker1_label=speaker_label,
        speaker2_label=speaker_label,
    )
