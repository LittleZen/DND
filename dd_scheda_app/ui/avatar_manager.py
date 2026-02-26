"""Avatar management - handles loading, changing, and saving character avatars."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from core import DataManager


def setup_avatar_manager(
    page: ft.Page,
    dm: DataManager,
    data: dict,
    schedule_save,
) -> ft.Container:
    """
    Set up avatar management UI and handlers.
    
    Args:
        page: Flet page reference
        dm: DataManager instance
        data: Character data dictionary (reference to dm.data)
        schedule_save: Function to schedule save operations
    
    Returns:
        Container with avatar display and controls
    """
    avatars_dir = Path(__file__).parent.parent / "img" / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    img_control = ft.Image(src="", width=650, height=180)
    image_inner = ft.Column([img_control], alignment=ft.MainAxisAlignment.CENTER)
    image_frame = ft.Container(content=image_inner, height=180, alignment=ft.Alignment(0, 0))
    avatar_status = ft.Text("Avatar caricato", size=10, color=ft.Colors.OUTLINE)

    def reload_avatar(e=None):
        """Load and display the current character's avatar."""
        try:
            dest = avatars_dir / f"avatar_{dm.current_character_id or 'default'}.png"
            if dest.exists():
                try:
                    with open(dest, "rb") as f:
                        b = f.read()
                    try:
                        import base64
                        b64 = base64.b64encode(b).decode("ascii")
                        data_uri = f"data:image/png;base64,{b64}"
                        new_img = ft.Image(src=data_uri, width=650, height=180)
                        new_container = ft.Container(content=new_img, padding=0, alignment=ft.Alignment(0, 0))
                    except Exception:
                        raise
                    try:
                        image_inner.controls[0] = new_container
                        image_inner.update()
                    except Exception:
                        try:
                            image_frame.content = new_container
                            image_frame.update()
                        except Exception:
                            fb = ft.Container(
                                content=ft.Column([
                                    ft.Icon(ft.Icons.PERSON, size=96),
                                    ft.Text("Avatar caricato (fallback)")
                                ], alignment=ft.MainAxisAlignment.CENTER),
                                alignment=ft.Alignment(0, 0),
                                height=180,
                            )
                            try:
                                image_frame.content = fb
                                image_frame.update()
                            except Exception:
                                img_control = new_container
                    try:
                        avatar_status.value = f"Avatar caricato: {dest.name} ({dest.stat().st_size} bytes)"
                        avatar_status.update()
                    except Exception:
                        pass
                    try:
                        page.snack_bar = ft.SnackBar(ft.Text(f"Avatar caricato: {dest.name}"))
                        page.snack_bar.open = True
                    except Exception:
                        pass
                except Exception:
                    pass
                page.update()
            else:
                fb = ft.Container(content=ft.Text("Nessun avatar trovato in img/avatars"), alignment=ft.Alignment(0, 0), height=180)
                try:
                    image_frame.content = fb
                    image_frame.update()
                except Exception:
                    pass
                page.snack_bar = ft.SnackBar(ft.Text("Nessun avatar trovato in img/avatars"))
                page.snack_bar.open = True
                page.update()
        except Exception:
            page.snack_bar = ft.SnackBar(ft.Text("Errore nel caricamento dell'avatar"))
            page.snack_bar.open = True
            page.update()

    return {
        "image_frame": image_frame,
        "image_inner": image_inner,
        "avatar_status": avatar_status,
        "reload_avatar": reload_avatar,
        "avatars_dir": avatars_dir,
    }
