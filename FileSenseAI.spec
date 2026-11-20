# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [("assets/filesense-ai.svg", "assets"), ("assets/filesense-ai.ico", "assets")]
binaries = []
hiddenimports = []

# Optional packages are installed by scripts/build_windows.ps1. Collection is
# conditional so a keyword-only build can omit the large AI packages.
for package in ("sentence_transformers", "torch", "open_clip", "huggingface_hub", "openpyxl", "imagehash"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except (ImportError, ModuleNotFoundError):
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    ["src/filesense_ai/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FileSenseAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/filesense-ai.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FileSenseAI")
