"""Make web-sized copies of the original photos in images/.

- Headshots (every other folder, plus the PI's photo in PI/) become square
  600x600 JPEGs in assets/people/, e.g. "Isabella Ashman.png" -> isabella-ashman.jpg
- Photos in images/section images/ and images/project images/ keep their shape,
  are resized (1600 / 1200 px wide at most), and go to assets/sections/ and
  assets/projects/, e.g. "Overview Image.jfif" -> assets/sections/overview-image.jpg

Originals are never modified. Re-run after adding new photos:

    python scripts/optimize_images.py
"""
import re
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "images"
# Folders of non-headshot photos -> (where their web copies go, max width in px,
# shape to crop to as width/height, or None to keep the photo's own shape).
# Project photos are all cropped to 4:3 so the project cards match.
UNCROPPED = {"section images": ("sections", 1600, None),
             "project images": ("projects", 1200, 4 / 3)}
HEADSHOT_SIZE = 600   # headshots are this many pixels square
EXTS = {".png", ".jpg", ".jpeg", ".jfif", ".webp", ".tif", ".tiff"}

# Where to center the square crop, for headshots where the middle isn't right.
# (x, y) are fractions of the width/height where the face is;
# zoom < 1 crops tighter (e.g. 0.5 = square half the photo's short side).
# Headshots not listed here are cropped around the center.
FOCUS = {
    "dr-elliott-arnold": (0.48, 0.45, 1.0),
    "isabella-ashman": (0.52, 0.48, 1.0),
    "james-simpson": (0.50, 0.50, 0.35),
    "chloe-mattie":  (0.37, 0.70, 0.6),
    "kenny-sidhu":   (0.45, 0.30, 1.0),
    "lilah-rathman": (0.45, 0.62, 0.45),
    "meagan-lipka":  (0.76, 0.40, 1.0),
    "sydney-costa":  (0.52, 0.41, 1.0),
    "dillon-letherer": (0.68, 0.30, 0.8),
    "emily-mero":    (0.48, 0.35, 0.6),
    "parker-lane":   (0.50, 0.33, 0.65),
    "michael-powell": (0.38, 0.17, 0.65),
    # project photos (zoom is ignored; they are cropped to their folder's shape)
    "peten-itza":    (0.50, 0.37, 1.0),
}


def slug(name: str) -> str:
    """'Dr. Elliott Arnold' -> 'dr-elliott-arnold'"""
    return "-".join(re.sub(r"[^\w\s-]", "", name.lower()).split())


def square_crop(im: Image.Image, x: float, y: float, zoom: float) -> Image.Image:
    w, h = im.size
    side = int(min(w, h) * zoom)
    # center the square on (x, y), but keep it inside the photo
    left = min(max(int(x * w - side / 2), 0), w - side)
    top = min(max(int(y * h - side / 2), 0), h - side)
    return im.crop((left, top, left + side, top + side))


def aspect_crop(im: Image.Image, aspect: float, x: float, y: float) -> Image.Image:
    """Crop to width/height = aspect, as large as possible, centered near (x, y)."""
    w, h = im.size
    cw, ch = (w, round(w / aspect)) if w / h < aspect else (round(h * aspect), h)
    left = min(max(int(x * w - cw / 2), 0), w - cw)
    top = min(max(int(y * h - ch / 2), 0), h - ch)
    return im.crop((left, top, left + cw, top + ch))


def main() -> None:
    for path in sorted(SRC.rglob("*")) + sorted((ROOT / "PI").glob("*")):
        if path.suffix.lower() not in EXTS:
            continue
        name = slug(path.stem)
        folder, width, aspect = next((UNCROPPED[p] for p in path.parts if p in UNCROPPED),
                                     (None, 0, None))
        section = folder is not None
        dest = ROOT / "assets" / (folder or "people")
        dest.mkdir(parents=True, exist_ok=True)
        out = dest / f"{name}.jpg"
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")  # respect phone rotation
            if section:
                if aspect:
                    x, y, _ = FOCUS.get(name, (0.5, 0.5, 1.0))
                    im = aspect_crop(im, aspect, x, y)
                im.thumbnail((width, width * 2), Image.LANCZOS)
            else:
                im = square_crop(im, *FOCUS.get(name, (0.5, 0.5, 1.0)))
                im = im.resize((HEADSHOT_SIZE, HEADSHOT_SIZE), Image.LANCZOS)
            im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
        kb = out.stat().st_size // 1024
        limit = 400 if section else 200
        warn = f"  <-- over {limit} KB" if kb > limit else ""
        print(f"{path.relative_to(ROOT)}  ->  {out.relative_to(ROOT)}  "
              f"({im.width}x{im.height}, {kb} KB){warn}")


if __name__ == "__main__":
    main()
