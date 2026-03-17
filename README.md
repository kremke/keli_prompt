# Keli Prompt — TTS Generator

Converts plain text and Markdown scripts into narrated MP3 audio using the
Google Gemini TTS API. Supports single-speaker and dual-speaker narration.

Designed for strong screen reader compatibility (NVDA and other Windows
assistive technologies).

---

## Requirements

- Windows 10 or later
- A [Google AI Studio](https://aistudio.google.com/) API key
- [ffmpeg](https://ffmpeg.org/download.html) in your system PATH (required for
  MP3 export; voice preview works without it)

---

## Running from source (Windows)

```bat
conda create -n keli_prompt python=3.12 -y
conda activate keli_prompt
pip install -r requirements.txt
python main.py
```

---

## Building the Windows executable

### Option A — GitHub Actions (no Windows machine needed)

1. Push the repository to GitHub.
2. Go to **Actions → Build Windows executable → Run workflow**.
3. Download the `KelihPrompt-windows` artifact from the completed run.
4. Extract and run `KelihPrompt.exe`.

A zip is also attached automatically to any release created by pushing a
version tag (`git tag v1.0.0 && git push --tags`).

### Option B — Build locally on Windows

```bat
conda activate keli_prompt
pip install -r requirements-dev.txt
build.bat
```

Output: `dist\KelihPrompt\KelihPrompt.exe`

---

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Entry point |
| `main_window.py` | PySide6 UI |
| `settings.py` | JSON settings persistence |
| `markdown_utils.py` | Markdown normalisation for TTS |
| `chunking.py` | Sentence-based and heading-based chunking |
| `prompts.py` | Single / dual-speaker prompt templates |
| `api_client.py` | Google Gemini TTS API calls |
| `audio_utils.py` | PCM → WAV playback, pydub MP3 export |
| `workers.py` | QThread worker with progress signals |
| `keli_prompt.spec` | PyInstaller build spec |
| `build.bat` | Windows build helper script |
