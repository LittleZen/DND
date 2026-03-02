from pathlib import Path
import base64
import logging
import flet as ft


def image_container_from_path(path: Path, width: int = 96, height: int = 96):
    """Return an ft.Container with the image loaded and embedded as base64 data URI.

    Returns None on failure.
    """
    try:
        p = Path(path)
        if not p.exists():
            return None
        with open(p, "rb") as f:
            b = f.read()
        b64 = base64.b64encode(b).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"
        img = ft.Image(src=data_uri, width=width, height=height)
        return ft.Container(
            content=img,
            width=width,
            height=height,
            border_radius=width // 2,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
    except Exception:
        logging.exception("Failed to build image container from %s", path)
        return None
