"""Stage a clean, pinned Windows browser distribution, never a user's profile."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

VERSION = "152.0.4"
BUILD = "beta.30"
SHA256 = "ea52a02fb1cfb1813ef6a326bea03fb2b650c9774143d953a94a27bfc8f10072"
URL = f"https://github.com/daijro/camoufox/releases/download/v{VERSION}-{BUILD}/camoufox-{VERSION}-{BUILD}-win.x86_64.zip"
root = Path(__file__).resolve().parents[1] / "build" / "browser-runtime"
root.mkdir(parents=True, exist_ok=True)
archive = root / f"camoufox-{VERSION}-{BUILD}.zip"
if not archive.exists():
    partial = archive.with_suffix('.download')
    print("Downloading pinned Camoufox distribution...", flush=True)
    urllib.request.urlretrieve(URL, partial)
    with partial.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == SHA256, "Browser checksum mismatch"
    partial.replace(archive)
with archive.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == SHA256, "Browser checksum mismatch"
target = root / f"camoufox-{VERSION}-{BUILD}"
target.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as zipped:
    for entry in zipped.infolist():
        destination = (target / entry.filename).resolve()
        if not destination.is_relative_to(target.resolve()):
            raise ValueError("Browser archive path escapes output directory")
    zipped.extractall(target)
(target / 'version.json').write_text(json.dumps({"version": VERSION, "build": BUILD, "sha256": SHA256}), encoding='utf-8')
assert (target / 'camoufox.exe').is_file() and (target / 'properties.json').is_file()
print(f"BROWSER: {target}", flush=True)
