#!/usr/bin/env python3
"""Convert an AVIF (or other) image to PNG and place it in img/avatars.

Usage:
  python convert_avif_to_png.py --src ../img/icons/your.avif --dest ../img/avatars/avatar_default.png

The script first tries Pillow; if that fails it will try `ffmpeg` then ImageMagick (`magick convert`).
"""
import argparse
import subprocess
from pathlib import Path
import sys

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False


def convert_with_pillow(src: Path, dest: Path):
    im = Image.open(src)
    im.save(dest, format="PNG")


def convert_with_ffmpeg(src: Path, dest: Path):
    cmd = ["ffmpeg", "-y", "-i", str(src), str(dest)]
    subprocess.check_call(cmd)


def convert_with_magick(src: Path, dest: Path):
    # ImageMagick v7 uses `magick convert` on some installs
    cmd = ["magick", "convert", str(src), str(dest)]
    subprocess.check_call(cmd)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True, help="Source image path (e.g. img/icons/file.avif)")
    p.add_argument(
        "--dest",
        required=False,
        help="Destination path (default: img/avatars/avatar_default.png)",
    )
    args = p.parse_args()

    src = Path(args.src)
    if not src.exists():
        print("Source file not found:", src)
        sys.exit(2)

    avatars_dir = Path(__file__).parent.parent / "img" / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    dest = Path(args.dest) if args.dest else avatars_dir / "avatar_default.png"

    # Try Pillow first
    if PIL_OK:
        try:
            print("Trying Pillow to convert...")
            convert_with_pillow(src, dest)
            print("Converted with Pillow ->", dest)
            return 0
        except Exception as e:
            print("Pillow conversion failed:", e)

    # Try ffmpeg
    try:
        print("Trying ffmpeg to convert...")
        convert_with_ffmpeg(src, dest)
        print("Converted with ffmpeg ->", dest)
        return 0
    except Exception as e:
        print("ffmpeg conversion failed:", e)

    # Try ImageMagick
    try:
        print("Trying ImageMagick to convert...")
        convert_with_magick(src, dest)
        print("Converted with ImageMagick ->", dest)
        return 0
    except Exception as e:
        print("ImageMagick conversion failed:", e)

    print("All conversion methods failed. Please convert the image to PNG/JPG manually and put it in img/avatars/")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
