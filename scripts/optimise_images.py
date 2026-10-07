#!/usr/bin/env python3
"""Shrink oversized photos and remove their metadata, in place.

Phone photos are often 4 to 8 MB and carry hidden metadata, including the GPS
location where they were taken. This script runs before every build: it rotates
each photo upright, resizes anything larger than needed, and saves it again
without metadata. Filenames and formats are unchanged, so nothing that refers
to a photo needs editing. Files already small and clean are left alone, so photos are never
re-compressed twice.

    python scripts/optimise_images.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "static" / "images"
MAX_SIDE = {"people": 900}          # portraits are shown small
DEFAULT_MAX_SIDE = 2000             # everything else
EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def has_metadata(im):
    exif = im.getexif()
    return bool(len(exif)) or "exif" in im.info or "xmp" in im.info or "XML:com.adobe.xmp" in im.info


def process(path):
    max_side = MAX_SIDE.get(path.parent.name, DEFAULT_MAX_SIDE)
    with Image.open(path) as im:
        im.load()
        fmt = im.format
        needs_resize = max(im.size) > max_side
        needs_clean = has_metadata(im)
        if not (needs_resize or needs_clean):
            return None
        before = path.stat().st_size
        icc = im.info.get("icc_profile")         # keep colour profiles (e.g. iPhone Display P3)
        out = ImageOps.exif_transpose(im)          # honour the camera's rotation before dropping it
        if max(out.size) > max_side:
            out.thumbnail((max_side, max_side), Image.LANCZOS)
        if fmt == "JPEG":
            out.convert("RGB").save(path, "JPEG", quality=85, optimize=True, progressive=True, icc_profile=icc)
        elif fmt == "WEBP":
            out.save(path, "WEBP", quality=85, method=6, icc_profile=icc)
        elif fmt == "PNG":
            out.save(path, "PNG", optimize=True, icc_profile=icc)
        else:
            return None
    return before, path.stat().st_size


def main():
    changed = 0
    for path in sorted(IMAGES.rglob("*")):
        if path.suffix.lower() not in EXTS or not path.is_file():
            continue
        try:
            result = process(path)
        except Exception as e:  # noqa: BLE001
            print(f"skipped {path.relative_to(ROOT)}: {e}", file=sys.stderr)
            continue
        if result:
            changed += 1
            before, after = result
            print(f"optimised {path.relative_to(ROOT)}: {before // 1024} KB -> {after // 1024} KB")
    print(f"{changed} image(s) optimised")


if __name__ == "__main__":
    main()
