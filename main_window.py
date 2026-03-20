"""Main application window for Keli Prompt.

Accessibility design notes
--------------------------
* Every interactive control has an explicit accessibleName so NVDA and other
  screen readers announce it correctly when it receives focus.
* QLabel.setBuddy() is used for every label/field pair so screen readers
  associate the label text with the field.
* Controls are *disabled* rather than hidden when not relevant (per spec).
  Hiding controls removes them from the tab order entirely, which disorients
  screen reader users who rely on a consistent, predictable structure.
* A QStatusBar mirrors every log message so screen readers that monitor the
  Windows status bar get live announcements without the user having to navigate
  to the log area.
* Tab order is set explicitly in _set_tab_order() in top-to-bottom, logical
  reading order.
* No dynamic focus shifts are performed.
"""

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QAccessible, QAccessibleValueChangeEvent, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from api_client import KNOWN_VOICES, generate_audio_dual, generate_audio_single, refresh_voices
from audio_utils import combine_and_export_mp3, export_chunk_mp3, play_pcm_audio
from chunking import create_chunks
from markdown_utils import normalize_text_for_tts
from prompts import (
    build_dual_prompt,
    build_single_prompt,
    build_voice_test_prompt_dual,
    build_voice_test_prompt_single,
)
from settings import load_settings, load_temp_script, save_settings, save_temp_script
from workers import Worker


class MainWindow(QMainWindow):
    """Primary application window."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Keli Prompt — TTS Generator")
        self.resize(900, 980)
        self.setMinimumSize(760, 600)

        self._settings: dict = load_settings()
        self._thread: Optional[QThread] = None
        self._worker: Optional[Worker] = None
        self._voice_thread: Optional[QThread] = None
        self._voice_worker: Optional[Worker] = None

        # Debounce autosave so we don't write on every keystroke
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(10_000)   # 10 s after last edit
        self._autosave_timer.timeout.connect(self._autosave_script)

        # Periodic autosave regardless of edits
        self._periodic_save_timer = QTimer(self)
        self._periodic_save_timer.setInterval(30_000)
        self._periodic_save_timer.timeout.connect(self._autosave_script)
        self._periodic_save_timer.start()

        self._build_ui()
        self._populate_from_settings()
        self._restore_temp_script()
        self._update_mode_ui()
        self._set_tab_order()

    # ------------------------------------------------------------------
    # Top-level UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Status bar — mirrors last log line for screen readers
        self._status_bar = QStatusBar()
        self._status_bar.setAccessibleName("Status bar showing latest progress message")
        self.setStatusBar(self._status_bar)

        # Use a plain QWidget — no QScrollArea wrapper.
        # QScrollArea at the top level causes NVDA to enter browse/virtual-cursor
        # mode and intercept keystrokes rather than passing them to the app.
        # A resizable QMainWindow with a direct layout keeps NVDA in
        # application/forms mode throughout.
        container = QWidget()
        self.setCentralWidget(container)

        root = QVBoxLayout(container)
        root.setSpacing(14)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(self._build_mode_section())
        root.addWidget(self._build_api_output_section())
        root.addWidget(self._build_input_section())
        root.addWidget(self._build_speaker_section())
        root.addWidget(self._build_chunking_section())
        root.addWidget(self._build_actions_section())
        root.addWidget(self._build_log_section())
        root.addStretch()

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    # ---- Section 1: Mode -----------------------------------------------

    def _build_mode_section(self) -> QGroupBox:
        box = QGroupBox("Mode")
        layout = QVBoxLayout(box)

        lbl = QLabel("Narration &mode:")
        lbl.setAccessibleName("Narration mode label")
        layout.addWidget(lbl)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Single Speaker", userData="single")
        self.mode_combo.addItem("Dual Speaker", userData="dual")
        self.mode_combo.setAccessibleName(
            "Narration mode. Single Speaker or Dual Speaker."
        )
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        lbl.setBuddy(self.mode_combo)
        layout.addWidget(self.mode_combo)

        return box

    # ---- Section 2: API and output -------------------------------------

    def _build_api_output_section(self) -> QGroupBox:
        box = QGroupBox("API and Output")
        layout = QVBoxLayout(box)

        # API key
        api_lbl = QLabel("&API Key (Google AI Studio):")
        api_lbl.setAccessibleName("API key label")
        layout.addWidget(api_lbl)

        api_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Paste your Google AI Studio API key here")
        self.api_key_edit.setAccessibleName(
            "API key field. This is a password field. "
            "Tab to the Show Key button to reveal the text."
        )
        self.api_key_edit.setAccessibleDescription(
            "Enter your Google AI Studio API key. Stored in settings."
        )
        api_lbl.setBuddy(self.api_key_edit)
        api_row.addWidget(self.api_key_edit)

        self.show_key_btn = QPushButton("Show Key")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setAccessibleName("Show or hide the API key")
        self.show_key_btn.toggled.connect(self._on_toggle_key_visibility)
        api_row.addWidget(self.show_key_btn)
        layout.addLayout(api_row)

        # Output folder
        out_lbl = QLabel("&Output folder:")
        out_lbl.setAccessibleName("Output folder label")
        layout.addWidget(out_lbl)

        out_row = QHBoxLayout()
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("Select or type the output folder path")
        self.output_folder_edit.setAccessibleName(
            "Output folder path. Tab to Browse button to open a folder dialog."
        )
        out_lbl.setBuddy(self.output_folder_edit)
        out_row.addWidget(self.output_folder_edit)

        self.browse_output_btn = QPushButton("Browse…")
        self.browse_output_btn.setAccessibleName("Browse for output folder, opens folder dialog")
        self.browse_output_btn.clicked.connect(self._on_browse_output)
        out_row.addWidget(self.browse_output_btn)
        layout.addLayout(out_row)

        # Base filename
        fn_lbl = QLabel("&Base filename (without extension):")
        fn_lbl.setAccessibleName("Base filename label")
        layout.addWidget(fn_lbl)

        self.base_filename_edit = QLineEdit()
        self.base_filename_edit.setPlaceholderText("e.g. route_training")
        self.base_filename_edit.setAccessibleName(
            "Base filename without extension. "
            "The final file will be named base filename dot mp3."
        )
        fn_lbl.setBuddy(self.base_filename_edit)
        layout.addWidget(self.base_filename_edit)

        return box

    # ---- Section 3: Input ----------------------------------------------

    def _build_input_section(self) -> QGroupBox:
        box = QGroupBox("Input")
        layout = QVBoxLayout(box)

        btn_row = QHBoxLayout()
        self.open_txt_btn = QPushButton("Open Text File (.txt)")
        self.open_txt_btn.setAccessibleName(
            "Open plain text file, loads content into script editor"
        )
        self.open_txt_btn.clicked.connect(self._on_open_txt)
        btn_row.addWidget(self.open_txt_btn)

        self.open_md_btn = QPushButton("Open Markdown File (.md)")
        self.open_md_btn.setAccessibleName(
            "Open Markdown file, loads content into script editor"
        )
        self.open_md_btn.clicked.connect(self._on_open_md)
        btn_row.addWidget(self.open_md_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        script_lbl = QLabel("Script (&paste text here or use a button above to load a file):")
        script_lbl.setAccessibleName("Script editor label")
        layout.addWidget(script_lbl)

        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlaceholderText(
            "Paste your script here or load a file with the buttons above.\n\n"
            "For dual-speaker mode, use labels like:\n\n"
            "Host:\nWelcome to the show.\n\n"
            "Instructor:\nThanks for having me."
        )
        self.script_edit.setMinimumHeight(200)
        self.script_edit.setAccessibleName("Script editor. Multi-line text area for your script.")
        self.script_edit.setAccessibleDescription(
            "Paste or load your full script here. "
            "In dual-speaker mode prefix lines with the speaker label followed by a colon."
        )
        script_lbl.setBuddy(self.script_edit)
        self.script_edit.textChanged.connect(self._on_script_changed)
        layout.addWidget(self.script_edit)

        return box

    # ---- Section 4: Speaker configuration -----------------------------

    def _build_speaker_section(self) -> QGroupBox:
        box = QGroupBox("Speaker Configuration")
        layout = QVBoxLayout(box)

        # --- Single speaker controls ---
        # All controls are always visible; _update_mode_ui enables/disables them.

        single_heading = QLabel("Single speaker settings:")
        single_heading.setAccessibleName("Single speaker settings group heading")
        layout.addWidget(single_heading)

        single_voice_lbl = QLabel("&Voice (single speaker mode):")
        single_voice_lbl.setAccessibleName("Single speaker voice selector label")
        layout.addWidget(single_voice_lbl)

        self.single_voice_combo = QComboBox()
        self.single_voice_combo.setAccessibleName(
            "Voice for single speaker mode. Disabled in dual speaker mode."
        )
        single_voice_lbl.setBuddy(self.single_voice_combo)
        layout.addWidget(self.single_voice_combo)

        # --- Dual speaker controls ---

        dual_heading = QLabel("Dual speaker settings:")
        dual_heading.setAccessibleName("Dual speaker settings group heading")
        layout.addWidget(dual_heading)

        sp1_label_lbl = QLabel("Speaker &1 label (must match label used in script):")
        sp1_label_lbl.setAccessibleName("Speaker 1 label field description")
        layout.addWidget(sp1_label_lbl)

        self.sp1_label_edit = QLineEdit()
        self.sp1_label_edit.setPlaceholderText("e.g. Host")
        self.sp1_label_edit.setAccessibleName(
            "Speaker 1 label. Must match the label in the script exactly, "
            "case insensitive. Disabled in single speaker mode."
        )
        sp1_label_lbl.setBuddy(self.sp1_label_edit)
        layout.addWidget(self.sp1_label_edit)

        sp1_voice_lbl = QLabel("Speaker 1 &voice:")
        sp1_voice_lbl.setAccessibleName("Speaker 1 voice selector label")
        layout.addWidget(sp1_voice_lbl)

        self.sp1_voice_combo = QComboBox()
        self.sp1_voice_combo.setAccessibleName(
            "Voice for speaker 1. Disabled in single speaker mode."
        )
        sp1_voice_lbl.setBuddy(self.sp1_voice_combo)
        layout.addWidget(self.sp1_voice_combo)

        sp2_label_lbl = QLabel("Speaker &2 label (must match label used in script):")
        sp2_label_lbl.setAccessibleName("Speaker 2 label field description")
        layout.addWidget(sp2_label_lbl)

        self.sp2_label_edit = QLineEdit()
        self.sp2_label_edit.setPlaceholderText("e.g. Instructor")
        self.sp2_label_edit.setAccessibleName(
            "Speaker 2 label. Must match the label in the script exactly, "
            "case insensitive. Disabled in single speaker mode."
        )
        sp2_label_lbl.setBuddy(self.sp2_label_edit)
        layout.addWidget(self.sp2_label_edit)

        sp2_voice_lbl = QLabel("Speaker 2 v&oice:")
        sp2_voice_lbl.setAccessibleName("Speaker 2 voice selector label")
        layout.addWidget(sp2_voice_lbl)

        self.sp2_voice_combo = QComboBox()
        self.sp2_voice_combo.setAccessibleName(
            "Voice for speaker 2. Disabled in single speaker mode."
        )
        sp2_voice_lbl.setBuddy(self.sp2_voice_combo)
        layout.addWidget(self.sp2_voice_combo)

        # --- Voice action buttons ---
        voice_btn_row = QHBoxLayout()

        self.refresh_voices_btn = QPushButton("Refresh Voices")
        self.refresh_voices_btn.setAccessibleName(
            "Refresh voice list from Google API. "
            "Verifies your API key and reloads available voices."
        )
        self.refresh_voices_btn.clicked.connect(self._on_refresh_voices)
        voice_btn_row.addWidget(self.refresh_voices_btn)

        self.voice_test_btn = QPushButton("Test Voice")
        self.voice_test_btn.setAccessibleName(
            "Test selected voice in single speaker mode. "
            "Generates and plays a short audio sample. "
            "Disabled in dual speaker mode."
        )
        self.voice_test_btn.clicked.connect(self._on_voice_test_single)
        voice_btn_row.addWidget(self.voice_test_btn)

        self.voice_test_sp1_btn = QPushButton("Test Speaker 1 Voice")
        self.voice_test_sp1_btn.setAccessibleName(
            "Test speaker 1 voice in dual speaker mode. "
            "Generates and plays a short audio sample. "
            "Disabled in single speaker mode."
        )
        self.voice_test_sp1_btn.clicked.connect(self._on_voice_test_sp1)
        voice_btn_row.addWidget(self.voice_test_sp1_btn)

        self.voice_test_sp2_btn = QPushButton("Test Speaker 2 Voice")
        self.voice_test_sp2_btn.setAccessibleName(
            "Test speaker 2 voice in dual speaker mode. "
            "Generates and plays a short audio sample. "
            "Disabled in single speaker mode."
        )
        self.voice_test_sp2_btn.clicked.connect(self._on_voice_test_sp2)
        voice_btn_row.addWidget(self.voice_test_sp2_btn)

        voice_btn_row.addStretch()
        layout.addLayout(voice_btn_row)

        return box

    # ---- Section 5: Chunking ------------------------------------------

    def _build_chunking_section(self) -> QGroupBox:
        box = QGroupBox("Chunking")
        layout = QVBoxLayout(box)

        cm_lbl = QLabel("Chunking &mode:")
        cm_lbl.setAccessibleName("Chunking mode label")
        layout.addWidget(cm_lbl)

        self.chunking_mode_combo = QComboBox()
        self.chunking_mode_combo.addItem("Sentence Based", userData="sentence")
        self.chunking_mode_combo.addItem("Heading Based", userData="heading")
        self.chunking_mode_combo.setAccessibleName(
            "Chunking mode. Sentence Based splits at sentence boundaries. "
            "Heading Based splits at document headings."
        )
        cm_lbl.setBuddy(self.chunking_mode_combo)
        layout.addWidget(self.chunking_mode_combo)

        cs_lbl = QLabel("Target chunk &size in characters:")
        cs_lbl.setAccessibleName("Target chunk size label")
        layout.addWidget(cs_lbl)

        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(500, 20_000)
        self.chunk_size_spin.setSingleStep(100)
        self.chunk_size_spin.setValue(4500)
        self.chunk_size_spin.setAccessibleName(
            "Target chunk size in characters. Default is 4500. "
            "The actual split point extends to the next sentence boundary."
        )
        cs_lbl.setBuddy(self.chunk_size_spin)
        layout.addWidget(self.chunk_size_spin)

        self.speak_headings_check = QCheckBox("Speak headings in audio")
        self.speak_headings_check.setAccessibleName(
            "Speak headings in audio checkbox. "
            "When checked, heading text is spoken aloud. "
            "When unchecked, headings are used only as chunk boundaries."
        )
        layout.addWidget(self.speak_headings_check)

        self.save_chunks_check = QCheckBox("Save individual chunk files")
        self.save_chunks_check.setAccessibleName(
            "Save individual chunk MP3 files checkbox. "
            "When checked, each chunk is also saved as a separate MP3 file."
        )
        layout.addWidget(self.save_chunks_check)

        self.combine_chunks_check = QCheckBox("Combine chunks into final MP3")
        self.combine_chunks_check.setAccessibleName(
            "Combine chunks into one final MP3 file checkbox. "
            "When checked, all chunks are merged into a single output file."
        )
        layout.addWidget(self.combine_chunks_check)

        return box

    # ---- Section 6: Actions -------------------------------------------

    def _build_actions_section(self) -> QGroupBox:
        box = QGroupBox("Actions")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()

        self.preview_chunks_btn = QPushButton("Preview Chunks")
        self.preview_chunks_btn.setAccessibleName(
            "Preview chunks. Shows how the script will be divided into chunks in the status log."
        )
        self.preview_chunks_btn.clicked.connect(self._on_preview_chunks)
        row.addWidget(self.preview_chunks_btn)

        self.generate_btn = QPushButton("Generate Audio")
        self.generate_btn.setAccessibleName(
            "Generate audio. Sends script to Google Gemini TTS and exports MP3."
        )
        self.generate_btn.clicked.connect(self._on_generate)
        row.addWidget(self.generate_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setAccessibleName(
            "Cancel. Stops the current generation or voice test. "
            "Disabled when no operation is running."
        )
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        row.addWidget(self.cancel_btn)

        self.open_output_btn = QPushButton("Open Output Folder")
        self.open_output_btn.setAccessibleName(
            "Open output folder in Windows Explorer."
        )
        self.open_output_btn.clicked.connect(self._on_open_output_folder)
        row.addWidget(self.open_output_btn)

        row.addStretch()
        layout.addLayout(row)

        return box

    # ---- Section 7: Status log ----------------------------------------

    def _build_log_section(self) -> QGroupBox:
        box = QGroupBox("Status Log")
        layout = QVBoxLayout(box)

        log_lbl = QLabel("Status messages (read only):")
        log_lbl.setAccessibleName("Status log label")
        layout.addWidget(log_lbl)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setTabChangesFocus(True)   # Tab moves to next control, not trapped here
        self.log_edit.setMinimumHeight(160)
        self.log_edit.setAccessibleName(
            "Status log, read only. "
            "Shows progress and error messages in order. "
            "Navigate here to review the full history."
        )
        self.log_edit.setAccessibleDescription(
            "All status messages from the current session are appended here. "
            "The most recent message is also shown in the status bar at the bottom of the window."
        )
        log_lbl.setBuddy(self.log_edit)
        layout.addWidget(self.log_edit)

        return box

    # ------------------------------------------------------------------
    # Tab order (top to bottom, logical reading order)
    # ------------------------------------------------------------------

    def _set_tab_order(self) -> None:
        order = [
            self.mode_combo,
            self.api_key_edit,
            self.show_key_btn,
            self.output_folder_edit,
            self.browse_output_btn,
            self.base_filename_edit,
            self.open_txt_btn,
            self.open_md_btn,
            self.script_edit,
            # Speaker section
            self.single_voice_combo,
            self.sp1_label_edit,
            self.sp1_voice_combo,
            self.sp2_label_edit,
            self.sp2_voice_combo,
            self.refresh_voices_btn,
            self.voice_test_btn,
            self.voice_test_sp1_btn,
            self.voice_test_sp2_btn,
            # Chunking section
            self.chunking_mode_combo,
            self.chunk_size_spin,
            self.speak_headings_check,
            self.save_chunks_check,
            self.combine_chunks_check,
            # Actions section
            self.preview_chunks_btn,
            self.generate_btn,
            self.cancel_btn,
            self.open_output_btn,
            # Log
            self.log_edit,
        ]
        for i in range(len(order) - 1):
            self.setTabOrder(order[i], order[i + 1])

    # ------------------------------------------------------------------
    # Settings population
    # ------------------------------------------------------------------

    def _populate_from_settings(self) -> None:
        s = self._settings

        # Mode
        idx = self.mode_combo.findData(s.get("mode", "single"))
        self.mode_combo.setCurrentIndex(max(0, idx))

        # API / output
        self.api_key_edit.setText(s.get("api_key", ""))
        self.output_folder_edit.setText(s.get("output_folder", ""))
        self.base_filename_edit.setText(s.get("base_filename", "output"))

        # Speaker labels
        self.sp1_label_edit.setText(s.get("dual_speaker1_label", "Host"))
        self.sp2_label_edit.setText(s.get("dual_speaker2_label", "Instructor"))

        # Chunking
        cidx = self.chunking_mode_combo.findData(s.get("chunking_mode", "sentence"))
        self.chunking_mode_combo.setCurrentIndex(max(0, cidx))
        self.chunk_size_spin.setValue(int(s.get("target_chunk_size", 4500)))
        self.speak_headings_check.setChecked(bool(s.get("speak_headings", True)))
        self.save_chunks_check.setChecked(bool(s.get("save_chunk_files", False)))
        self.combine_chunks_check.setChecked(bool(s.get("combine_chunks", True)))

        # Voices — populate with known catalogue first
        self._populate_voice_combos(KNOWN_VOICES)

        # Restore saved selections
        for combo, key in [
            (self.single_voice_combo, "single_voice"),
            (self.sp1_voice_combo, "dual_voice1"),
            (self.sp2_voice_combo, "dual_voice2"),
        ]:
            saved = s.get(key, "")
            if saved:
                i = combo.findText(saved)
                if i >= 0:
                    combo.setCurrentIndex(i)

        self.log("Settings loaded.")
        self.log("API key loaded." if s.get("api_key") else "No API key set.")
        self.log("Voice list populated from built-in catalogue.")

    def _populate_voice_combos(self, voices: List[str]) -> None:
        """Refill all three voice combo boxes, preserving current selection."""
        for combo, key in [
            (self.single_voice_combo, "single_voice"),
            (self.sp1_voice_combo, "dual_voice1"),
            (self.sp2_voice_combo, "dual_voice2"),
        ]:
            current = combo.currentText()
            preferred = self._settings.get(key, "") or current
            combo.clear()
            combo.addItems(voices)
            restore = combo.findText(preferred)
            if restore >= 0:
                combo.setCurrentIndex(restore)

    def _restore_temp_script(self) -> None:
        text = load_temp_script()
        if text:
            self.script_edit.setPlainText(text)
            self.log("Recovered unsaved script from previous session.")

    # ------------------------------------------------------------------
    # Collect UI state → settings dict
    # ------------------------------------------------------------------

    def _collect_settings(self) -> dict:
        s = self._settings.copy()
        s["api_key"] = self.api_key_edit.text().strip()
        s["output_folder"] = self.output_folder_edit.text().strip()
        s["base_filename"] = self.base_filename_edit.text().strip()
        s["mode"] = self.mode_combo.currentData()
        s["dual_speaker1_label"] = self.sp1_label_edit.text().strip()
        s["dual_speaker2_label"] = self.sp2_label_edit.text().strip()
        s["single_voice"] = self.single_voice_combo.currentText()
        s["dual_voice1"] = self.sp1_voice_combo.currentText()
        s["dual_voice2"] = self.sp2_voice_combo.currentText()
        s["chunking_mode"] = self.chunking_mode_combo.currentData()
        s["target_chunk_size"] = self.chunk_size_spin.value()
        s["speak_headings"] = self.speak_headings_check.isChecked()
        s["save_chunk_files"] = self.save_chunks_check.isChecked()
        s["combine_chunks"] = self.combine_chunks_check.isChecked()
        return s

    # ------------------------------------------------------------------
    # Mode UI update — ALWAYS use setEnabled, never setVisible
    # Hiding controls removes them from the screen reader's tab order.
    # ------------------------------------------------------------------

    def _update_mode_ui(self) -> None:
        is_dual = self.mode_combo.currentData() == "dual"

        # Single-mode-only controls
        self.single_voice_combo.setEnabled(not is_dual)
        self.voice_test_btn.setEnabled(not is_dual)

        # Dual-mode-only controls
        self.sp1_label_edit.setEnabled(is_dual)
        self.sp1_voice_combo.setEnabled(is_dual)
        self.sp2_label_edit.setEnabled(is_dual)
        self.sp2_voice_combo.setEnabled(is_dual)
        self.voice_test_sp1_btn.setEnabled(is_dual)
        self.voice_test_sp2_btn.setEnabled(is_dual)

    # ------------------------------------------------------------------
    # Logging — also updates status bar for live screen reader announcements
    # ------------------------------------------------------------------

    def log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_edit.setTextCursor(cursor)
        # Status bar text update
        self._status_bar.showMessage(message)
        # Fire a UIA value-change event on the status bar so NVDA announces
        # the new message as a live region without the user navigating to it.
        if QAccessible.isActive():
            try:
                event = QAccessibleValueChangeEvent(self._status_bar, message)
                QAccessible.updateAccessibility(event)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Busy state — disables action buttons; keeps them *visible*
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self.generate_btn.setEnabled(not busy)
        self.preview_chunks_btn.setEnabled(not busy)
        self.refresh_voices_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        if not busy:
            self._update_mode_ui()  # restore mode-dependent enabled states
        else:
            # Disable voice test buttons during any operation
            self.voice_test_btn.setEnabled(False)
            self.voice_test_sp1_btn.setEnabled(False)
            self.voice_test_sp2_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_mode_changed(self) -> None:
        self._update_mode_ui()

    def _on_toggle_key_visibility(self, checked: bool) -> None:
        if checked:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("Hide Key")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("Show Key")

    def _on_browse_output(self) -> None:
        start = self.output_folder_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if folder:
            self.output_folder_edit.setText(folder)

    def _on_open_txt(self) -> None:
        self._open_file("Text files (*.txt);;All files (*.*)")

    def _on_open_md(self) -> None:
        self._open_file("Markdown files (*.md);;Text files (*.txt);;All files (*.*)")

    def _open_file(self, file_filter: str) -> None:
        start = self._settings.get("last_input_folder", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, "Open Script File", start, file_filter)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.script_edit.setPlainText(text)
            self._settings["last_input_folder"] = str(Path(path).parent)
            self.log(f"Script loaded: {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "File Error", f"Could not open the file:\n{exc}")

    def _on_script_changed(self) -> None:
        # Restart debounce timer — save 10 s after the last keystroke
        self._autosave_timer.start()

    def _autosave_script(self) -> None:
        save_temp_script(self.script_edit.toPlainText())

    # ---- Refresh voices ------------------------------------------------

    def _on_refresh_voices(self) -> None:
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(
                self, "API Key Missing",
                "Please enter your Google AI Studio API key before refreshing voices."
            )
            return
        self.log("Refreshing voice list…")
        self._set_busy(True)

        def task(worker: Worker, key: str) -> None:
            worker.progress.emit("Contacting Google AI to verify API key…")
            voices = refresh_voices(key)
            worker.progress.emit(f"Voice list loaded: {len(voices)} voices available.")
            worker._voice_list = voices  # type: ignore[attr-defined]

        self._voice_thread = QThread()
        self._voice_worker = Worker(task, api_key)
        self._voice_worker.moveToThread(self._voice_thread)
        self._voice_thread.started.connect(self._voice_worker.run)
        self._voice_worker.progress.connect(self.log)
        self._voice_worker.finished.connect(self._on_voice_refresh_done)
        self._voice_worker.error.connect(self._on_voice_refresh_error)
        self._voice_worker.finished.connect(self._voice_worker.deleteLater)
        self._voice_thread.finished.connect(self._voice_thread.deleteLater)
        self._voice_thread.start()

    def _on_voice_refresh_done(self) -> None:
        voices = getattr(self._voice_worker, "_voice_list", KNOWN_VOICES)
        self._populate_voice_combos(voices)
        if self._voice_thread:
            self._voice_thread.quit()
        self._set_busy(False)
        self.log("Voices refreshed.")

    def _on_voice_refresh_error(self, msg: str) -> None:
        self.log(f"Voice refresh error: {msg}")
        if self._voice_thread:
            self._voice_thread.quit()
        self._set_busy(False)
        QMessageBox.warning(
            self, "Voice Refresh Failed",
            f"Could not refresh voices from the API:\n{msg}\n\n"
            "The built-in voice catalogue is still available."
        )

    # ---- Voice tests ---------------------------------------------------

    def _on_voice_test_single(self) -> None:
        api_key = self.api_key_edit.text().strip()
        voice = self.single_voice_combo.currentText()
        if not api_key:
            QMessageBox.warning(self, "Missing API Key", "Enter your API key first.")
            return
        if not voice:
            QMessageBox.warning(self, "No Voice Selected", "Select a voice first.")
            return
        self.log(f"Testing voice: {voice}…")
        self._set_busy(True)
        self._run_playback_worker(build_voice_test_prompt_single(), api_key, voice)

    def _on_voice_test_sp1(self) -> None:
        self._voice_test_dual_speaker(
            self.sp1_label_edit.text().strip() or "Speaker1",
            self.sp1_voice_combo.currentText(),
        )

    def _on_voice_test_sp2(self) -> None:
        self._voice_test_dual_speaker(
            self.sp2_label_edit.text().strip() or "Speaker2",
            self.sp2_voice_combo.currentText(),
        )

    def _voice_test_dual_speaker(self, label: str, voice: str) -> None:
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Missing API Key", "Enter your API key first.")
            return
        if not voice:
            QMessageBox.warning(self, "No Voice Selected", f"Select a voice for {label} first.")
            return
        self.log(f"Testing voice for {label}: {voice}…")
        self._set_busy(True)
        # Voice test uses single-speaker API so we only hear the chosen voice clearly
        prompt = build_voice_test_prompt_dual(label)
        self._run_playback_worker(prompt, api_key, voice)

    def _run_playback_worker(self, prompt: str, api_key: str, voice: str) -> None:
        def task(worker: Worker, p: str, key: str, v: str) -> None:
            worker.progress.emit("Generating preview audio…")
            audio = generate_audio_single(key, p, v)
            worker.progress.emit("Playing preview audio…")
            play_pcm_audio(audio)
            worker.progress.emit("Voice preview complete.")

        self._thread = QThread()
        self._worker = Worker(task, prompt, api_key, voice)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.log)
        self._worker.finished.connect(self._on_task_finished)
        self._worker.error.connect(self._on_task_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    # ---- Preview chunks -----------------------------------------------

    def _on_preview_chunks(self) -> None:
        text = self.script_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty Script", "The script editor is empty.")
            return

        speak_headings = self.speak_headings_check.isChecked()
        normalized = normalize_text_for_tts(text, speak_headings)
        mode = self.chunking_mode_combo.currentData()
        target = self.chunk_size_spin.value()
        chunks = create_chunks(normalized, mode, target)

        self.log(f"--- Chunk preview: {len(chunks)} chunk(s) ---")
        for i, chunk in enumerate(chunks):
            lines = [ln for ln in chunk.splitlines() if ln.strip()]
            preview_lines = lines[:3]
            preview = "\n".join(preview_lines)
            if len(lines) > 3:
                preview += "\n…"
            self.log(
                f"Chunk {i + 1} of {len(chunks)} — {len(chunk)} characters:\n"
                f"{preview}\n"
            )
        self.log("--- End of chunk preview ---")

    # ---- Generate audio -----------------------------------------------

    def _on_generate(self) -> None:
        s = self._collect_settings()
        save_settings(s)
        self._settings = s

        # --- Input validation ---
        api_key = s["api_key"]
        if not api_key:
            QMessageBox.critical(
                self, "Missing API Key",
                "Enter your Google AI Studio API key in the API and Output section."
            )
            return

        text = self.script_edit.toPlainText().strip()
        if not text:
            QMessageBox.critical(self, "Empty Script", "The script editor is empty.")
            return

        output_folder = s["output_folder"]
        if not output_folder or not Path(output_folder).is_dir():
            QMessageBox.critical(
                self, "Invalid Output Folder",
                "The output folder does not exist. Select a valid folder."
            )
            return

        base_filename = s["base_filename"].strip()
        if not base_filename:
            QMessageBox.critical(
                self, "Missing Filename",
                "Enter a base filename in the API and Output section."
            )
            return

        mode = s["mode"]
        voice = s["single_voice"]
        sp1_label = s["dual_speaker1_label"]
        sp1_voice = s["dual_voice1"]
        sp2_label = s["dual_speaker2_label"]
        sp2_voice = s["dual_voice2"]

        if mode == "single" and not voice:
            QMessageBox.critical(
                self, "No Voice Selected",
                "Select a voice in the Speaker Configuration section."
            )
            return
        if mode == "dual":
            missing = []
            if not sp1_label:
                missing.append("Speaker 1 label")
            if not sp1_voice:
                missing.append("Speaker 1 voice")
            if not sp2_label:
                missing.append("Speaker 2 label")
            if not sp2_voice:
                missing.append("Speaker 2 voice")
            if missing:
                QMessageBox.critical(
                    self, "Incomplete Speaker Configuration",
                    "The following fields are required for dual speaker mode:\n"
                    + "\n".join(f"  • {m}" for m in missing)
                )
                return

        if not s["save_chunk_files"] and not s["combine_chunks"]:
            QMessageBox.warning(
                self, "Nothing to Save",
                "Both 'Save individual chunk files' and 'Combine chunks into final MP3' "
                "are unchecked. Enable at least one."
            )
            return

        self.log("=== Audio generation started ===")
        self._set_busy(True)

        # Capture local copies of all settings for the worker closure
        _mode = mode
        _voice = voice
        _sp1_label = sp1_label
        _sp1_voice = sp1_voice
        _sp2_label = sp2_label
        _sp2_voice = sp2_voice
        _speak_headings = s["speak_headings"]
        _chunking_mode = s["chunking_mode"]
        _target_size = s["target_chunk_size"]
        _save_chunks = s["save_chunk_files"]
        _combine = s["combine_chunks"]
        _output_folder = output_folder
        _base_filename = base_filename

        def task(worker: Worker, raw_text: str, _api_key: str) -> None:
            # Step 1: Normalise
            worker.progress.emit("Normalising script text…")
            normalized = normalize_text_for_tts(raw_text, _speak_headings)

            # Step 2: Chunk
            worker.progress.emit("Chunking script…")
            chunks = create_chunks(normalized, _chunking_mode, _target_size)
            if not chunks:
                raise ValueError(
                    "No text chunks were produced. Check that the script is not empty."
                )
            worker.progress.emit(f"Chunking complete: {len(chunks)} chunk(s) created.")

            # Step 3: Generate audio per chunk
            pcm_chunks: List[bytes] = []
            for i, chunk in enumerate(chunks):
                if worker.is_cancelled:
                    worker.progress.emit("Generation cancelled.")
                    return

                worker.progress.emit(
                    f"Generating chunk {i + 1} of {len(chunks)}…"
                )

                if _mode == "single":
                    prompt = build_single_prompt(chunk)
                    audio = generate_audio_single(_api_key, prompt, _voice)
                else:
                    prompt = build_dual_prompt(chunk, _sp1_label, _sp2_label)
                    audio = generate_audio_dual(
                        _api_key, prompt,
                        _sp1_label, _sp1_voice,
                        _sp2_label, _sp2_voice,
                    )

                pcm_chunks.append(audio)
                worker.progress.emit(f"Chunk {i + 1} of {len(chunks)} generated.")

            if worker.is_cancelled:
                worker.progress.emit("Generation cancelled.")
                return

            # Step 4: Export
            out_dir = Path(_output_folder)

            if _combine:
                worker.progress.emit("Combining audio chunks…")
                final_path = str(out_dir / f"{_base_filename}.mp3")
                chunk_base = str(out_dir / _base_filename) if _save_chunks else None
                combine_and_export_mp3(pcm_chunks, final_path, chunk_base, _save_chunks)
                worker.progress.emit(f"Final MP3 saved: {final_path}")
            else:
                # Save chunks only, no combined file
                worker.progress.emit("Saving individual chunk files…")
                for i, pcm in enumerate(pcm_chunks):
                    if worker.is_cancelled:
                        worker.progress.emit("Generation cancelled.")
                        return
                    cpath = str(out_dir / f"{_base_filename}_{i + 1:02d}.mp3")
                    export_chunk_mp3(pcm, cpath)
                    worker.progress.emit(f"Chunk file saved: {Path(cpath).name}")

            worker.progress.emit("=== Generation complete ===")

        self._thread = QThread()
        self._worker = Worker(task, text, api_key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.log)
        self._worker.finished.connect(self._on_task_finished)
        self._worker.error.connect(self._on_task_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    # ---- Cancel --------------------------------------------------------

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.log("Cancellation requested…")

    # ---- Open output folder --------------------------------------------

    def _on_open_output_folder(self) -> None:
        folder = self.output_folder_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(
                self, "Invalid Folder",
                "The output folder is not set or does not exist."
            )
            return
        import subprocess  # noqa: PLC0415
        subprocess.Popen(["explorer", folder])

    # ------------------------------------------------------------------
    # Worker callbacks
    # ------------------------------------------------------------------

    def _on_task_finished(self) -> None:
        if self._thread is not None:
            self._thread.quit()
        self._set_busy(False)

    def _on_task_error(self, msg: str) -> None:
        self.log(f"ERROR: {msg}")
        if self._thread is not None:
            self._thread.quit()
        self._set_busy(False)
        QMessageBox.critical(
            self, "Operation Failed",
            f"An error occurred:\n\n{msg}\n\n"
            "Check the status log for details."
        )

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.cancel()
        s = self._collect_settings()
        save_settings(s)
        save_temp_script(self.script_edit.toPlainText())
        super().closeEvent(event)
