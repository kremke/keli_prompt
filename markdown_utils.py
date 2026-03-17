"""Markdown processing utilities for Keli Prompt."""

import re


def is_heading(line: str) -> bool:
    """Return True if the line is a markdown or plain-text heading."""
    stripped = line.strip()
    if re.match(r'^#{1,3}\s+\S', stripped):
        return True
    if re.match(r'^(CHAPTER|SECTION)\s*:', stripped, re.IGNORECASE):
        return True
    return False


def extract_heading_text(line: str) -> str:
    """Return the plain text of a heading line, without markers."""
    stripped = line.strip()
    # Markdown heading
    md = re.match(r'^#+\s*(.*)', stripped)
    if md:
        return md.group(1).strip()
    # Plain-text CHAPTER / SECTION
    pt = re.match(r'^(CHAPTER|SECTION)\s*:\s*(.*)', stripped, re.IGNORECASE)
    if pt:
        return pt.group(0).strip()
    return stripped


def _strip_inline_markdown(text: str) -> str:
    """Remove inline markdown markers (bold, italic, code, links)."""
    # Bold / italic combinations
    text = re.sub(r'\*{3}(.+?)\*{3}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_{3}(.+?)_{3}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\*{2}(.+?)\*{2}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_{2}(.+?)_{2}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\*(.+?)\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_(.+?)_', r'\1', text, flags=re.DOTALL)
    # Inline code
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Links — keep visible text
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[(.+?)\]\(.*?\)', r'\1', text)
    # Horizontal rules
    text = re.sub(r'^\s*[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    return text


def normalize_text_for_tts(text: str, speak_headings: bool) -> str:
    """
    Prepare the full script text for TTS.

    - If speak_headings is True, headings become plain spoken text.
    - If False, heading markers are removed and the line is left blank
      (still used as chunk boundaries internally).
    - Bullet markers are stripped.
    - Inline markdown is stripped.
    """
    lines = text.split('\n')
    result: list[str] = []

    for line in lines:
        stripped = line.strip()

        if is_heading(stripped):
            heading_text = extract_heading_text(stripped)
            if speak_headings:
                result.append(heading_text)
            else:
                result.append('')
            continue

        # Bullet list items — strip the marker
        bullet = re.match(r'^[\*\-\+]\s+(.*)', stripped)
        if bullet:
            result.append(bullet.group(1))
            continue

        # Numbered list — keep the text
        numbered = re.match(r'^\d+[.)]\s+(.*)', stripped)
        if numbered:
            result.append(numbered.group(1))
            continue

        result.append(line)

    combined = '\n'.join(result)
    combined = _strip_inline_markdown(combined)
    # Collapse runs of 3+ blank lines to 2
    combined = re.sub(r'\n{3,}', '\n\n', combined)
    return combined.strip()
