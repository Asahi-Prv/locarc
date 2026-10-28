# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LocArc (onedir, windowed).

Build from the repository root:

    python -m PyInstaller --noconfirm --clean locarc.spec

The output is written to ``dist/LocArc/`` and can be zipped and shipped
as-is. Paths in ``datas`` are resolved relative to this spec file, so the spec
must stay in the repository root.
"""

a = Analysis(
    ["locarc.py"],
    pathex=[],
    binaries=[],
    datas=[("app/static", "app/static"), ("app/linux_window.py", "app/linux_window.py")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Heavy ML packages are only used by the on-demand tokenizer converter, which
    # installs them into the OVMS runtime (not into the app). Never bundle them.
    excludes=[
        "openvino",
        "openvino_tokenizers",
        "transformers",
        "tokenizers",
        "numpy",
        "scipy",
        "pandas",
        "sklearn",
        "torch",
        "tensorflow",
        "jax",
        "flax",
        "sentencepiece",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocArc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LocArc",
)
