@echo off
REM -----------------------------------------------------------------------
REM Keli Prompt — Windows build script
REM Run this from the project root inside the activated conda environment.
REM
REM Prerequisites:
REM   conda activate keli_prompt
REM   pip install pyinstaller
REM   ffmpeg in PATH (for pydub MP3 export at runtime)
REM -----------------------------------------------------------------------

echo [build] Checking PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [build] PyInstaller not found. Installing...
    pip install pyinstaller
)

echo [build] Cleaning previous build artefacts...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [build] Running PyInstaller...
pyinstaller keli_prompt.spec

if errorlevel 1 (
    echo.
    echo [build] ERROR: PyInstaller failed. See output above.
    exit /b 1
)

echo.
echo [build] Build complete.
echo [build] Executable is in:  dist\KelihPrompt\KelihPrompt.exe
echo.
echo [build] REMINDER: The target machine must have ffmpeg.exe in PATH
echo [build] for MP3 export to work.  Voice preview uses winsound and
echo [build] does NOT require ffmpeg.
