#!/usr/bin/env python3
"""
Generate RoleMule icons from the master mark.

Thin neon line-art disappears at 16–36px. This script:
  1. Builds a transparent full mark for navbar UI (`docs/rolemule-icon.png`)
  2. Builds a face-only favicon (head + cyan eye — pack dropped for tiny sizes)
  3. Writes Chrome extension icons (face-only at 16/48; fuller at 128)

Source of truth for the original artwork:
  docs/rolemule-icon.original.png  (thin line art — do not overwrite lightly)
  docs/rolemule-icon.png           (navbar mark; transparent bg)

Requirements:
    pip install Pillow

Usage:
    python generate_icons.py
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "docs" / "rolemule-icon.original.png"
MASTER_FALLBACK = ROOT / "docs" / "rolemule-icon.png"
OUT_MASTER = ROOT / "docs" / "rolemule-icon.png"
UI_ICON = ROOT / "ui" / "static" / "img" / "rolemule-icon.png"
UI_FAVICON_PNG = ROOT / "ui" / "static" / "img" / "favicon.png"
UI_FAVICON_PNG_ROOT = ROOT / "ui" / "static" / "favicon.png"
UI_FAVICON_SVG = ROOT / "ui" / "static" / "img" / "favicon.svg"
UI_FAVICON_ICO = ROOT / "ui" / "static" / "favicon.ico"
OUT_DIR = Path(__file__).resolve().parent


def _source_image() -> Image.Image:
    path = ORIGINAL if ORIGINAL.exists() else MASTER_FALLBACK
    if not path.exists():
        raise SystemExit(f"Master icon not found: {path}")
    return Image.open(path).convert("RGBA")


def _split_masks(img: Image.Image) -> tuple[Image.Image, Image.Image]:
    w, h = img.size
    pixels = img.load()
    white_mask = Image.new("L", (w, h), 0)
    cyan_mask = Image.new("L", (w, h), 0)
    wm, cm = white_mask.load(), cyan_mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 30 or r + g + b < 60:
                continue
            if b > 160 and g > 140 and r < 140 and (b + g) > r * 2.2:
                cm[x, y] = 255
            elif max(r, g, b) > 120:
                wm[x, y] = 255
    return white_mask, cyan_mask


def _thicken(mask: Image.Image, passes: int, radius: int = 5) -> Image.Image:
    out = mask
    for _ in range(passes):
        out = out.filter(ImageFilter.MaxFilter(radius))
    return out


def _apply_rounded_alpha(img: Image.Image, radius_ratio: float = 0.18) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, w - 1, h - 1),
        radius=int(w * radius_ratio),
        fill=255,
    )
    out = img.copy()
    out.putalpha(mask)
    return out


def build_master(src: Image.Image) -> Image.Image:
    """Navbar / large UI mark — light stroke boost only (favicons use heavier make_small)."""
    w, h = src.size
    white_mask, cyan_mask = _split_masks(src)
    white_thick = _thicken(white_mask, passes=1, radius=3)
    cyan_thick = _thicken(cyan_mask, passes=1, radius=3)
    glow = white_thick.filter(ImageFilter.GaussianBlur(radius=3))

    # Transparent canvas — mule blends with navbar (any page bg)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    wt, ct = white_thick.load(), cyan_thick.load()
    wg = glow.load()
    white = (250, 252, 255)
    cyan = (0, 220, 255)
    cyan_core = (150, 250, 255)

    for y in range(h):
        for x in range(w):
            if wt[x, y] > 100:
                op[x, y] = (*white, 255)
            elif ct[x, y] > 100:
                color = cyan_core if cyan_mask.getpixel((x, y)) > 80 else cyan
                op[x, y] = (*color, 255)
            else:
                gv = wg[x, y]
                if gv > 20:
                    a = int(min(255, gv * 0.35))
                    op[x, y] = (255, 255, 255, a)
                else:
                    op[x, y] = (0, 0, 0, 0)

    return out


def make_favicon_face(src: Image.Image, size: int, passes: int) -> Image.Image:
    """Face-only favicon — head, ears, cyan eye. Pack dropped for 16–32px legibility."""
    w, h = src.size
    # Pack sits on the left/back; crop to the head region
    crop = src.crop((int(w * 0.29), int(h * 0.06), int(w * 0.90), int(h * 0.76)))
    scale = 4
    big = size * scale
    base = crop.resize((big, big), Image.Resampling.LANCZOS)
    # Slight extra zoom into the face
    zw = int(big * 0.08)
    base = base.crop((zw, zw, big - zw, big - zw)).resize((big, big), Image.Resampling.LANCZOS)

    white_mask, cyan_mask = _split_masks(base)
    white_thick = _thicken(white_mask, passes=passes, radius=3)
    cyan_thick = _thicken(cyan_mask, passes=max(1, passes - 1), radius=3)
    glow = white_thick.filter(ImageFilter.GaussianBlur(radius=1.0))

    # Solid dark tile for browser tabs (--bg-primary)
    bg = (10, 10, 15)
    canvas = Image.new("RGBA", (big, big), (*bg, 255))
    cp = canvas.load()
    for y in range(big):
        for x in range(big):
            r, g, b = bg
            gv = glow.getpixel((x, y))
            if gv:
                f = gv / 255.0 * 0.15
                r = int(bg[0] * (1 - f) + 255 * f)
                g = int(bg[1] * (1 - f) + 255 * f)
                b = int(bg[2] * (1 - f) + 255 * f)
            if white_thick.getpixel((x, y)) > 100:
                r, g, b = 255, 255, 255
            if cyan_thick.getpixel((x, y)) > 100:
                r, g, b = 80, 240, 255
            cp[x, y] = (r, g, b, 255)

    return _apply_rounded_alpha(canvas, radius_ratio=0.22).resize(
        (size, size), Image.Resampling.LANCZOS
    )


def make_small(src: Image.Image, size: int, passes: int) -> Image.Image:
    """High-legibility icon at an exact pixel size (Chrome extension icons)."""
    scale = 4
    big = size * scale
    base = src.resize((big, big), Image.Resampling.LANCZOS)
    white_mask, cyan_mask = _split_masks(base)
    white_thick = _thicken(white_mask, passes=passes, radius=3)
    cyan_thick = _thicken(cyan_mask, passes=max(1, passes - 1), radius=3)
    glow = white_thick.filter(ImageFilter.GaussianBlur(radius=2))

    canvas = Image.new("RGBA", (big, big), (10, 10, 15, 255))
    cp = canvas.load()
    for y in range(big):
        for x in range(big):
            r, g, b = 10, 10, 15
            gv = glow.getpixel((x, y))
            if gv:
                f = gv / 255.0 * 0.5
                r = int(10 * (1 - f) + 255 * f)
                g = int(10 * (1 - f) + 255 * f)
                b = int(15 * (1 - f) + 255 * f)
            if white_thick.getpixel((x, y)) > 100:
                r, g, b = 255, 255, 255
            if cyan_thick.getpixel((x, y)) > 100:
                r, g, b = 80, 240, 255
            cp[x, y] = (r, g, b, 255)

    return _apply_rounded_alpha(canvas).resize((size, size), Image.Resampling.LANCZOS)


def _write_favicon_svg(png: Image.Image, path: Path) -> None:
    buf = io.BytesIO()
    png.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        f'  <image href="data:image/png;base64,{b64}" width="32" height="32"/>\n'
        "</svg>\n",
        encoding="utf-8",
    )


def main() -> None:
    src = _source_image()
    print(f"Source: {ORIGINAL if ORIGINAL.exists() else MASTER_FALLBACK}")
    print("-" * 40)

    master = build_master(src)
    master.save(OUT_MASTER)
    UI_ICON.parent.mkdir(parents=True, exist_ok=True)
    master.save(UI_ICON)
    # Popup header uses the same full mark as the app navbar
    (OUT_DIR / "brand-icon.png").write_bytes(UI_ICON.read_bytes())
    print(f"Wrote {OUT_MASTER.relative_to(ROOT)} (navbar — full mule + pack, transparent)")
    print(f"Wrote {UI_ICON.relative_to(ROOT)}")
    print("Wrote extension/icons/brand-icon.png (popup header)")

    fav32 = make_favicon_face(src, 32, 1)
    fav16 = make_favicon_face(src, 16, 2)
    fav32.save(UI_FAVICON_PNG)
    fav32.save(UI_FAVICON_PNG_ROOT)
    _write_favicon_svg(fav32, UI_FAVICON_SVG)
    try:
        fav16.save(
            UI_FAVICON_ICO,
            format="ICO",
            sizes=[(16, 16), (32, 32)],
            append_images=[fav32],
        )
    except TypeError:
        fav32.save(UI_FAVICON_ICO, format="ICO", sizes=[(32, 32)])
    print("Wrote favicon.png / favicon.svg / favicon.ico (face-only)")

    print("-" * 40)
    # Extension toolbar icons must match the website favicon exactly (same art).
    for size, name in (
        (16, "icon16.png"),
        (48, "icon48.png"),
        (128, "icon128.png"),
    ):
        path = OUT_DIR / name
        fav32.resize((size, size), Image.Resampling.LANCZOS).save(path)
        print(f"Created {path.name} ({size}x{size}) — scaled from website favicon")

    print("-" * 40)
    print("All icons generated successfully!")
    print("Hard-refresh the browser (favicon is cached aggressively).")
    print("Reload the Chrome extension at chrome://extensions/")


if __name__ == "__main__":
    main()
