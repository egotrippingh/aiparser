"""Package the existing website logo as a multi-resolution Windows ICO.

Run with the project's Python environment; no EXE build is performed.
"""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend/public/assets/brand/airvision-icon-graphite.png"
TARGET = ROOT / "assets/airate.ico"
SIZES = [(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)]


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as source:
        source.convert("RGBA").save(TARGET, format="ICO", sizes=SIZES)
    with Image.open(TARGET) as icon:
        if icon.ico.sizes() != set(SIZES):
            raise RuntimeError("Windows icon is missing required resolutions")
    print(TARGET)


if __name__ == "__main__":
    main()
