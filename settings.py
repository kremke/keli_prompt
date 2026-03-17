"""Settings persistence for Keli Prompt."""

import json
from pathlib import Path

APP_DIR = Path.home() / ".keli_prompt"
SETTINGS_FILE = APP_DIR / "settings.json"
TEMP_SCRIPT_FILE = APP_DIR / "temp_script.txt"

DEFAULT_SETTINGS: dict = {
    "api_key": "",
    "output_folder": str(Path.home() / "Documents"),
    "mode": "single",
    "chunking_mode": "sentence",
    "target_chunk_size": 4500,
    "single_voice": "",
    "dual_speaker1_label": "Host",
    "dual_speaker2_label": "Instructor",
    "dual_voice1": "",
    "dual_voice2": "",
    "speak_headings": True,
    "save_chunk_files": False,
    "combine_chunks": True,
    "last_input_folder": str(Path.home()),
    "base_filename": "output",
}


def load_settings() -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = DEFAULT_SETTINGS.copy()
            result.update(data)
            return result
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def save_temp_script(text: str) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(TEMP_SCRIPT_FILE, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def load_temp_script() -> str:
    if TEMP_SCRIPT_FILE.exists():
        try:
            with open(TEMP_SCRIPT_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return ""
