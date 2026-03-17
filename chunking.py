"""Chunking logic for Keli Prompt."""

from typing import List
from markdown_utils import is_heading, extract_heading_text

SENTENCE_ENDINGS = frozenset('.!?')


def _split_sentences(text: str, target: int, overflow: int = 800) -> List[str]:
    """
    Split *text* into chunks of approximately *target* characters.

    After reaching the target offset we scan forward up to *overflow* extra
    characters for a sentence boundary (.  !  ?  followed by whitespace or end
    of string).  If none is found we split at the nearest preceding whitespace.
    """
    chunks: List[str] = []
    pos = 0
    length = len(text)

    while pos < length:
        remaining = length - pos
        if remaining <= target:
            chunk = text[pos:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Search window ends either at target+overflow or end of text
        window_end = min(pos + target + overflow, length)
        window = text[pos:window_end]
        window_len = len(window)

        boundary: int | None = None

        # Scan forward from target offset looking for sentence boundary
        scan_start = min(target, window_len - 1)
        for i in range(scan_start, window_len):
            ch = window[i]
            if ch in SENTENCE_ENDINGS:
                # Accept if followed by whitespace, newline, or end-of-window
                next_i = i + 1
                if next_i >= window_len or window[next_i] in ' \t\n\r':
                    boundary = i + 1
                    break

        if boundary is None:
            # Fall back: nearest whitespace at or after target
            for i in range(min(target, window_len) - 1, window_len):
                if window[i] in ' \t\n\r':
                    boundary = i + 1
                    break

        if boundary is None:
            boundary = target

        chunk = text[pos:pos + boundary].strip()
        if chunk:
            chunks.append(chunk)
        # Advance past boundary, skipping leading whitespace
        pos += boundary
        while pos < length and text[pos] in ' \t':
            pos += 1

    return [c for c in chunks if c.strip()]


def _split_by_headings(text: str, target: int) -> List[str]:
    """
    Split text at heading boundaries.

    Each heading section is kept intact if it fits within *target*; otherwise
    it is further split using sentence rules.  The heading line is prepended to
    every sub-chunk produced from an oversized section.
    """
    lines = text.split('\n')
    sections: List[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_body: List[str] = []

    for line in lines:
        if is_heading(line.strip()):
            if current_body or current_heading is not None:
                sections.append((current_heading, '\n'.join(current_body).strip()))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)

    # Flush last section
    sections.append((current_heading, '\n'.join(current_body).strip()))

    chunks: List[str] = []
    for heading, body in sections:
        if heading:
            full = heading + '\n\n' + body if body else heading
        else:
            full = body

        if not full.strip():
            continue

        if len(full) <= target:
            chunks.append(full)
        else:
            # Need sub-chunking of the body
            sub_chunks = _split_sentences(body, target) if body else []
            if not sub_chunks:
                # Heading only, oversized is unlikely but handle it
                chunks.append(full[:target].strip())
            else:
                for sub in sub_chunks:
                    if heading:
                        chunks.append(heading + '\n\n' + sub)
                    else:
                        chunks.append(sub)

    return [c for c in chunks if c.strip()]


def create_chunks(
    text: str,
    mode: str = "sentence",
    target_size: int = 4500,
) -> List[str]:
    """
    Public entry point.

    *mode* is either ``"sentence"`` or ``"heading"``.
    Returns a list of non-empty chunk strings.
    """
    if mode == "heading":
        return _split_by_headings(text, target_size)
    return _split_sentences(text, target_size)
