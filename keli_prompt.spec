# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Keli Prompt
# Build with:  pyinstaller keli_prompt.spec
#
# Produces a --onedir bundle in dist\KelihPrompt\.
# onedir is preferred over onefile for PySide6: faster startup, no temp-extract
# overhead, and Qt's accessibility plugin loads more reliably.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # google-genai lazy imports
        'google.genai',
        'google.genai.types',
        'google.auth',
        'google.auth.transport',
        'google.auth.transport.requests',
        # pydub internals
        'pydub',
        'pydub.audio_segment',
        'pydub.utils',
        'pydub.effects',
        # Windows audio playback (stdlib, but ensure it's included)
        'winsound',
        # app modules
        'settings',
        'markdown_utils',
        'chunking',
        'prompts',
        'api_client',
        'audio_utils',
        'workers',
        'main_window',
    ],
    hookspath=[],
    hooksconfig={
        # Ensure the Qt accessibility bridge plugin is included.
        # This is essential for NVDA and other Windows screen readers.
        "PySide6": {
            "plugins": [
                "accessible",
                "platforms",
                "platformthemes",
                "styles",
                "imageformats",
            ],
        },
    },
    runtime_hooks=[],
    excludes=[
        # Trim unused heavy packages to keep bundle size down
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'tkinter',
        'PyQt5',
        'PyQt6',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KelihPrompt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no console window — GUI only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Application manifest — enables Windows UI Automation / MSAA so that
    # NVDA and other screen readers can inspect the application's controls.
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python*.dll'],
    name='KelihPrompt',
)
