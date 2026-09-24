"""PyInstaller one-folder build. User data and account credentials are external."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


root = Path(SPECPATH).resolve()
datas = [
    (str(root / "web"), "web"),
    (str(root / "app" / "db" / "schema.sql"), "app/db"),
    (str(root / "app" / "scanner" / "adapters" / "selectors.json"), "app/scanner/adapters"),
]
binaries = []
hiddenimports = []

for package in ("camoufox", "browserforge", "apify_fingerprint_datapoints",
                "language_tags", "playwright", "pymorphy3_dicts_ru"):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports

analysis = Analysis(
    [str(root / "desktop.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "server"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AI-Mentions",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="AI-Mentions",
)
