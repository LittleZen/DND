from pathlib import Path
import re
import sys
import threading
import random

sys.path.append(str(Path(__file__).parent))

import flet as ft
import base64
from .bank import normalize_money, to_int
from .core import DataManager
from .inventory import (
    DEFAULT_CATEGORY,
    normalize_inventory_items,
    parse_inventory_item,
    split_inventory_raw,
)
from .pdf_import import read_pdf_fields
from .settings import load_settings, save_settings
from .storage import (
    add_item_to_library,
    create_character,
    delete_character,
    delete_item_from_library,
    get_all_items,
    get_item_by_id,
    list_characters,
    load_character,
    save_character,
    update_item_in_library,
)

PDF_FILE = Path(__file__).parent / "scheda.pdf"


def main(page: ft.Page):
    page.title = "Scheda DD"
    page.window_width = 1230
    page.window_height = 900
    page.window_resizable = False
    page.window_min_width = 1230
    page.window_min_height = 900
    page.window_max_width = 1230
    page.window_max_height = 900
    page.padding = 24
    page.bgcolor = ft.Colors.SURFACE
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    settings = load_settings()
    theme_mode_setting = (settings.get("theme_mode") or "dark").lower()
    page.theme_mode = ft.ThemeMode.DARK if theme_mode_setting == "dark" else ft.ThemeMode.LIGHT

    # (floating debug button removed) 

    # Application state - centralized data management
    dm = DataManager()

    # For backward compatibility with existing code
    data = dm.data
    
    def schedule_save():
        """Wrapper for dm.schedule_save() - maintains backward compatibility."""
        dm.schedule_save()
    
    def do_save():
        """Wrapper for dm.do_save() - maintains backward compatibility."""
        dm.do_save()
    
    # Alias for current_character_id for backward compatibility  
    class CharacterIDRef:
        """Simple reference wrapper for current_character_id."""
        def __init__(self, dm_instance):
            self.dm = dm_instance
        
        def __eq__(self, other):
            return self.dm.current_character_id == other
        
        def __repr__(self):
            return str(self.dm.current_character_id)
    
    current_character_id_ref = CharacterIDRef(dm)

    # Basic UI fields that some handlers expect
    nome = ft.TextField(label="Nome", value=dm.data.get("nome", ""), expand=True)
    motivazione = ft.TextField(label="Motivazione", value=dm.data.get("motivazione", ""), expand=True)

    xp = ft.TextField(label="XP", value=data.get("xp_raw", ""), width=100)

    def xp_on_change(e):
        try:
            update_xp_background()
        except Exception:
            pass
        data["xp_raw"] = xp.value
        schedule_save()
        page.update()

    xp.on_change = xp_on_change

    def inc_xp(e):
        pct = get_xp_percent_int() + 1
        set_xp_percent(pct)
        page.update()

    def dec_xp(e):
        pct = get_xp_percent_int() - 1
        set_xp_percent(pct)
        page.update()

    xp_block = ft.Row(
        [
            ft.IconButton(icon=ft.Icons.REMOVE, on_click=dec_xp, icon_size=16),
            xp,
            ft.IconButton(icon=ft.Icons.ADD, on_click=inc_xp, icon_size=16),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def toggle_theme(e):
        page.theme_mode = (
            ft.ThemeMode.DARK if page.theme_mode == ft.ThemeMode.LIGHT else ft.ThemeMode.LIGHT
        )
        theme_toggle.icon = (
            ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE
        )
        settings["theme_mode"] = "dark" if page.theme_mode == ft.ThemeMode.DARK else "light"
        save_settings(settings)
        page.update()

    theme_toggle = ft.IconButton(
        icon=ft.Icons.DARK_MODE,
        tooltip="Dark mode",
        on_click=toggle_theme,
    )

    appunti = ft.TextField(
        label="Appunti",
        value=data.get("appunti", ""),
        prefix_icon=ft.Icons.NOTES,
        multiline=True,
        min_lines=16,
        max_lines=24,
        text_size=14,
        expand=True,
    )

    def on_appunti_change(e):
        data["appunti"] = appunti.value
        schedule_save()

    appunti.on_change = on_appunti_change

    def on_money_change(e):
        data["money"]["corone"] = to_int(corone.value)
        data["money"]["scellini"] = to_int(scellini.value)
        data["money"]["rame"] = to_int(rame.value)
        schedule_save()

    corone = ft.TextField(
        label="Corone",
        value=str(data.get("money", {}).get("corone", 0)),
        prefix_icon=ft.Icons.PAID,
        width=140,
        on_change=on_money_change,
    )
    scellini = ft.TextField(
        label="Scellini",
        value=str(data.get("money", {}).get("scellini", 0)),
        prefix_icon=ft.Icons.MONETIZATION_ON,
        width=140,
        on_change=on_money_change,
    )
    rame = ft.TextField(
        label="Rame",
        value=str(data.get("money", {}).get("rame", 0)),
        prefix_icon=ft.Icons.CURRENCY_BITCOIN,
        width=140,
        on_change=on_money_change,
    )

    def on_status_change(e):
        data["status"]["adrenalina"] = adrenalina_switch.value
        data["status"]["confusione"] = confusione_switch.value
        data["status"]["svantaggio"] = svantaggio_switch.value
        data["status"]["malus"] = malus.value
        schedule_save()

    adrenalina_switch = ft.Switch(
        label="Adrenalina",
        value=data.get("status", {}).get("adrenalina", False),
        active_color=ft.Colors.RED_400,
        on_change=on_status_change,
        tooltip="Nella prossima prova estrai almeno 4 token",
    )
    confusione_switch = ft.Switch(
        label="Confusione",
        value=data.get("status", {}).get("confusione", False),
        active_color=ft.Colors.ORANGE_400,
        on_change=on_status_change,
        tooltip="Nella prossima prova, per ogni token bianco che aggiungi al pool, devi pescare un token dal sacchetto e quello pescato sostituisce il bianco.",
    )
    svantaggio_switch = ft.Switch(
        label="Svantaggio",
        value=data.get("status", {}).get("svantaggio", False),
        active_color=ft.Colors.BLUE_400,
        on_change=on_status_change,
        tooltip="1 token nero aggiuntivo, se lanci i dadi: lancia 2 volte e prendi il risultato MINORE",
    )

    malus = ft.TextField(label="Malus", value=dm.data.get("status", {}).get("malus", "nulla"), expand=True, hint_text="nulla", tooltip="Inserisci il malus del tuo personaggio", on_change=on_status_change)

    inv_grid = ft.GridView(
        expand=True,
        runs_count=4,
        max_extent=180,
        child_aspect_ratio=1.1,
        spacing=10,
        run_spacing=10,
        padding=10,
    )
    qualita_list = ft.ListView(expand=True, spacing=8, padding=10)
    imparato_list = ft.ListView(expand=True, spacing=8, padding=10)

    CATEGORIES = [
        "materiale",
        "arma",
        "scudo",
        "pet",
        "elmo",
        "corazza",
        "pantaloni",
        "gambali",
        "zaino",
        "consumabile",
        "altro",
    ]

    CATEGORY_ICONS = {
        "materiale": ft.Icons.INVENTORY_2,
        "arma": ft.Icons.SPORTS_KABADDI,
        "scudo": ft.Icons.SHIELD,
        "pet": ft.Icons.PETS,
        "elmo": ft.Icons.SAFETY_DIVIDER,
        "corazza": ft.Icons.CHECKROOM,
        "pantaloni": ft.Icons.CHECKROOM_OUTLINED,
        "gambali": ft.Icons.ACCESSIBILITY_NEW,
        "zaino": ft.Icons.BACKPACK,
        "consumabile": ft.Icons.LOCAL_DRINK,
        "altro": ft.Icons.MORE_HORIZ,
    }

    def on_nome_change(e):
        data["nome"] = nome.value
        schedule_save()

    def on_motivazione_change(e):
        data["motivazione"] = motivazione.value
        schedule_save()

    nome.on_change = on_nome_change
    motivazione.on_change = on_motivazione_change

    def parse_xp_percent(value: str) -> float:
        if not value:
            return 0.0
        match = re.search(r"(\d+)", value)
        if not match:
            return 0.0
        pct = int(match.group(1))
        pct = max(0, min(100, pct))
        return pct / 100.0

    def get_xp_percent_int() -> int:
        return int(round(parse_xp_percent(xp.value) * 100))

    def update_xp_background():
        xp_progress.value = parse_xp_percent(xp.value)

    xp_container = ft.Container(
        content=xp,
        padding=0,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        expand=True,
    )

    xp_progress = ft.ProgressBar(
        value=0,
        height=3,
        bar_height=3,
        color=ft.Colors.PRIMARY_CONTAINER,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )

    xp_progress_wrap = ft.Container(
        content=ft.Row(
            [
                ft.Container(xp_progress, expand=True),
                ft.Container(width=32),
            ],
            spacing=6,
        ),
        margin=ft.Margin(top=-4, left=0, right=0, bottom=0),
    )

    def set_xp_percent(pct: int):
        pct = max(0, min(100, pct))
        # Disable on_change handler temporarily to avoid double-triggering
        xp.on_change = None
        xp.value = f"{pct}%"
        xp.on_change = xp_on_change
        # Update data directly and save
        data["xp_raw"] = xp.value
        update_xp_background()
        schedule_save()

    def sync_all_fields_to_data():
        """Unused function - can be removed"""
        pass

    def refresh_inventory():
        inv_grid.controls.clear()
        inventory = data.get("inventario", []) or []

        # Normalize items into dicts with name, qty, category and optional item_id
        normalized = []
        for it in inventory:
            if isinstance(it, dict):
                name = (it.get("name") or "").strip()
                qty = int(it.get("qty") or it.get("quantity") or 1)
                category = it.get("category") or DEFAULT_CATEGORY
                item_id = it.get("item_id")
            else:
                name, qty = parse_inventory_item(str(it))
                category = DEFAULT_CATEGORY
                item_id = None
            normalized.append({"name": name, "qty": max(1, qty), "category": category, "item_id": item_id})  

        def sort_key(it):
            cat = it.get("category") or DEFAULT_CATEGORY
            try:
                cat_idx = CATEGORIES.index(cat)
            except ValueError:
                cat_idx = 999
            nm = it.get("name") or ""
            return (cat_idx, nm.lower())

        for idx, it in enumerate(sorted(normalized, key=sort_key)):
            # Resolve library item if present
            lib = None
            if it.get("item_id"):
                try:
                    lib = get_item_by_id(it["item_id"]) or None
                except Exception:
                    lib = None

            item_name = (lib.get("name") if lib else it.get("name")) or ""
            item_effect = (lib.get("effect") if lib else None) or None
            icon_name = (lib.get("category") if lib else it.get("category")) or DEFAULT_CATEGORY
            icon = CATEGORY_ICONS.get(icon_name, ft.Icons.HELP_OUTLINE)
            qty_val = int(it.get("qty") or 1)

            qty_field = ft.TextField(value=str(qty_val), width=44, text_align=ft.TextAlign.CENTER, text_size=12)

            def on_inc(e, i=idx):
                try:
                    data["inventario"][i]["qty"] = int(data["inventario"][i].get("qty", 1)) + 1
                except Exception:
                    # fallback: if raw string, parse and replace
                    name, q = parse_inventory_item(str(data["inventario"][i]))
                    data["inventario"][i] = {"name": name, "qty": q + 1, "category": DEFAULT_CATEGORY}
                schedule_save()
                refresh_inventory()
                page.update()

            def on_dec(e, i=idx):
                try:
                    current = int(data["inventario"][i].get("qty", 1))
                    if current > 1:
                        data["inventario"][i]["qty"] = current - 1
                    else:
                        data["inventario"].pop(i)
                except Exception:
                    # fallback: remove
                    try:
                        data["inventario"].pop(i)
                    except Exception:
                        pass
                schedule_save()
                refresh_inventory()
                page.update()

            def on_delete(e, i=idx):
                try:
                    data["inventario"].pop(i)
                except Exception:
                    pass
                schedule_save()
                refresh_inventory()
                page.update()

            qty_field.on_change = lambda e, i=idx: (
                data["inventario"].__setitem__(i, {**(data.get("inventario")[i] if isinstance(data.get("inventario")[i], dict) else {}), "name": item_name, "qty": int(e.control.value or 1)}) or schedule_save()
            )

            card = ft.Container(
                content=ft.Stack(
                    [
                        # Contenuto centrato
                        ft.Column(
                            [
                                ft.Icon(icon, size=32, color=ft.Colors.PRIMARY),
                                ft.Text(item_name, size=12, weight=ft.FontWeight.BOLD, max_lines=2, text_align=ft.TextAlign.CENTER),
                                ft.Container(height=2),
                                ft.Row(
                                    [
                                        ft.IconButton(ft.Icons.REMOVE, on_click=on_dec, icon_size=14),
                                        qty_field,
                                        ft.IconButton(ft.Icons.ADD, on_click=on_inc, icon_size=14),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=4,
                        ),
                        # X posizionata in alto a destra
                        ft.Container(
                            content=ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                on_click=on_delete,
                                icon_size=16,
                                icon_color=ft.Colors.ERROR,
                                tooltip="Elimina",
                            ),
                            right=0,
                            top=0,
                        ),
                    ],
                ),
                padding=6,
                border_radius=8,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                tooltip=item_effect if item_effect else None,
            )

            inv_grid.controls.append(card)

    def add_item(e):
        data.setdefault("inventario", []).append(
            {"name": "Nuovo oggetto", "qty": 1, "category": DEFAULT_CATEGORY}
        )
        schedule_save()
        refresh_inventory()
        page.update()

    def import_from_pdf(e):
        if not PDF_FILE.exists():
            page.snack_bar = ft.SnackBar(ft.Text("PDF non trovato"))
            page.snack_bar.open = True
            page.update()
            return

        fields = read_pdf_fields(PDF_FILE)
        normalized_fields = {
            re.sub(r"[\s_]+", "", k).lower(): v for k, v in (fields or {}).items()
        }

        def pick(*keys):
            for key in keys:
                if key in fields and fields[key]:
                    return fields[key]
            return ""

        def pick_norm(*keys):
            for key in keys:
                cleaned = re.sub(r"[\s_]+", "", key).lower()
                val = normalized_fields.get(cleaned)
                if val:
                    return val
            return ""

        nome_val = pick("Nome", "nome") or pick_norm("nome", "nomepersonaggio", "personaggio")
        if nome_val:
            data["nome"] = nome_val

        motivazione_val = pick("Motivazione", "motivazione") or pick_norm("motivazione", "background")
        if motivazione_val:
            data["motivazione"] = motivazione_val

        appunti_val = pick("Appunti", "appunti") or pick_norm("appunti", "note", "notevarie")
        if appunti_val:
            data["appunti"] = appunti_val

        xp_val = pick("XP", "Px", "PX", "xp") or pick_norm("xp", "px")
        if xp_val:
            data["xp_raw"] = xp_val

        money = data.get("money", {})
        corone_val = pick("Corone", "corone") or pick_norm("corone")
        scellini_val = pick("Scellini", "scellini") or pick_norm("scellini")
        rame_val = pick("Rame", "rame") or pick_norm("rame")
        if corone_val:
            money["corone"] = to_int(corone_val)
        if scellini_val:
            money["scellini"] = to_int(scellini_val)
        if rame_val:
            money["rame"] = to_int(rame_val)
        data["money"] = normalize_money(money)

        inventario_val = pick("Inventario", "inventario", "Equipaggiamento", "equipaggiamento") or pick_norm(
            "inventario", "equipaggiamento"
        )
        if inventario_val:
            data["inventario_raw"] = inventario_val

        # inventario strutturato
        data["inventario"] = normalize_inventory_items(
            split_inventory_raw(data.get("inventario_raw", ""))
        )

        # aggiorna UI
        nome.value = data["nome"]
        motivazione.value = data["motivazione"]
        xp.value = data["xp_raw"]
        appunti.value = data["appunti"]

        schedule_save()
        refresh_inventory()

        page.snack_bar = ft.SnackBar(ft.Text("Import completato dal PDF ✅"))
        page.snack_bar.open = True
        page.update()

    def refresh_imparato():
        imparato_list.controls.clear()
        for i, it in enumerate(data.get("imparato", [])):
            txt = ft.TextField(value=it, expand=True)

            def on_change(e, idx=i):
                data["imparato"][idx] = e.control.value
                schedule_save()

            def on_delete(e, idx=i):
                try:
                    data["imparato"].pop(idx)
                except Exception:
                    pass
                schedule_save()
                refresh_imparato()
                page.update()

            txt.on_change = on_change

            imparato_list.controls.append(
                ft.Row(
                    [txt, ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=on_delete)],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

    refresh_inventory()

    def add_qualita(e):
        data.setdefault("qualita", []).append("Nuova qualità")
        schedule_save()
        refresh_qualita()
        page.update()

    def add_imparato(e):
        data.setdefault("imparato", []).append("Nuova conoscenza")
        schedule_save()
        refresh_imparato()
        page.update()

    def refresh_qualita():
        qualita_list.controls.clear()
        for i, it in enumerate(data.get("qualita", [])):
            txt = ft.TextField(value=it, expand=True)

            def on_change(e, idx=i):
                data["qualita"][idx] = e.control.value
                schedule_save()

            def on_delete(e, idx=i):
                try:
                    data["qualita"].pop(idx)
                except Exception:
                    pass
                schedule_save()
                refresh_qualita()
                page.update()

            txt.on_change = on_change

            qualita_list.controls.append(
                ft.Row(
                    [txt, ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=on_delete)],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

    def apply_data_to_fields():
        nome.value = data.get("nome", "")
        motivazione.value = data.get("motivazione", "")
        xp.value = data.get("xp_raw", "")
        appunti.value = data.get("appunti", "")
        # Load avatar from saved path if present, otherwise attempt reload from avatars folder
        try:
            avatar_path = data.get("avatar_path")
            if avatar_path:
                p = Path(avatar_path)
                if p.exists():
                    try:
                        with open(p, "rb") as f:
                            b = f.read()
                        data_uri = f"data:image/png;base64,{base64.b64encode(b).decode('ascii')}"
                        new_img = ft.Image(src=data_uri, width=96, height=96)
                        new_container = ft.Container(content=new_img, padding=0, alignment=ft.Alignment(0, 0))
                        try:
                            image_holder.content = new_container
                            image_holder.update()
                            try:
                                avatar_status.value = f"Avatar caricato: {p.name} ({p.stat().st_size} bytes)"
                                avatar_status.update()
                            except Exception:
                                pass
                        except Exception:
                            pass
                    except Exception:
                        pass
            else:
                # try to load any available avatar for current character
                reload_avatar()
        except Exception:
            pass
        # avatar is placeholder image for now
        money = normalize_money(data.get("money", {}))
        corone.value = str(money.get("corone", 0))
        scellini.value = str(money.get("scellini", 0))
        rame.value = str(money.get("rame", 0))
        # Update status switches
        status = data.get("status", {"adrenalina": False, "confusione": False, "svantaggio": False, "malus": ""})
        adrenalina_switch.value = status.get("adrenalina", False)
        confusione_switch.value = status.get("confusione", False)
        svantaggio_switch.value = status.get("svantaggio", False)
        malus.value = status.get("malus", "")
        update_xp_background()
        refresh_inventory()
        refresh_qualita()
        refresh_imparato()

    def load_character_by_id(character_id: int):
        dm.set_character(character_id)
        dm.data.update(load_character(character_id))
        dm.data["money"] = normalize_money(dm.data.get("money", {}))
        dm.data.setdefault("qualita", [])
        dm.data.setdefault("status", {"adrenalina": False, "confusione": False, "svantaggio": False, "malus": "nulla"})
        apply_data_to_fields()
        selector_view.visible = False
        editor_view.visible = True
        page.update()

    def go_back_to_selector(e=None):
        refresh_character_list()
        editor_view.visible = False
        selector_view.visible = True
        page.update()

    def refresh_character_list():
        character_grid.controls.clear()
        characters = list_characters()

        create_card = ft.Container(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.ADD_CIRCLE, size=80, color=ft.Colors.OUTLINE),
                        ft.Text("Crea nuovo personaggio", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    expand=True,
                ),
                height=160,
            ),
            on_click=create_new_character,
            padding=12,
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            bgcolor=ft.Colors.TRANSPARENT,
        )
        character_grid.controls.append(create_card)

        def build_avatar_thumb(character_id: int, avatar_path: str | None):
            # Priorità: 1) avatar_{id}.png, 2) avatar_path dal DB, 3) default
            candidates = [avatars_dir / f"avatar_{character_id}.png"]
            if avatar_path:
                p = Path(avatar_path)
                if not p.is_absolute():
                    p = (Path(__file__).parent / p).resolve()
                candidates.append(p)
            candidates.append(avatars_dir / "avatar_default.png")
            
            for path in candidates:
                if path.exists():
                    try:
                        with open(path, "rb") as f:
                            image_data = f.read()
                        b64_string = base64.b64encode(image_data).decode("ascii")
                        data_uri = f"data:image/png;base64,{b64_string}"
                        return ft.Container(
                            content=ft.Image(src=data_uri, width=96, height=96),
                            width=96,
                            height=96,
                            border_radius=48,
                            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        )
                    except Exception:
                        continue
            return ft.Icon(ft.Icons.PERSON, size=80, color=ft.Colors.OUTLINE)

        def confirm_delete_character(character_id: int, nome: str):
            def do_delete(ev):
                delete_character(character_id)
                page.dialog.open = False
                refresh_character_list()
                page.update()

            def cancel_delete(ev):
                page.dialog.open = False
                page.update()

            page.dialog = ft.AlertDialog(
                title=ft.Text("Elimina personaggio", weight=ft.FontWeight.BOLD),
                content=ft.Text(f"Vuoi eliminare '{nome}'?"),
                actions=[
                    ft.TextButton("Annulla", on_click=cancel_delete),
                    ft.TextButton("Elimina", on_click=do_delete),
                ],
            )
            page.dialog.open = True
            page.update()

        for ch in characters:
            avatar = build_avatar_thumb(ch["id"], ch.get("avatar_path"))
            
            # build card with avatar+name centered and a small round delete button anchored bottom-center
            top_block = ft.Container(
                content=ft.Column(
                    [avatar, ft.Text(ch["nome"], weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                on_click=lambda e, cid=ch["id"]: load_character_by_id(cid),
            )

            delete_control = ft.Container(
                content=ft.Icon(ft.Icons.CLOSE, color=ft.Colors.RED_400, size=16),
                width=32,
                height=32,
                alignment=ft.Alignment(0, 0),
                border_radius=16,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                on_click=lambda e, cid=ch["id"], nome=ch.get("nome", ""): confirm_delete_character(cid, nome),
            )

            card_inner = ft.Container(
                content=ft.Column(
                    [
                        top_block,
                        ft.Row([delete_control], alignment=ft.MainAxisAlignment.CENTER),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    expand=True,
                ),
                height=160,
            )

            final_card = ft.Container(
                content=card_inner,
                padding=12,
                border_radius=12,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                bgcolor=ft.Colors.SURFACE_CONTAINER,
            )
            character_grid.controls.append(final_card)

    def create_new_character(e):
        character_id = create_character("Senza nome")
        refresh_character_list()
        load_character_by_id(character_id)

    # Avatar icon for Dati Base - load from img/avatars folder
    avatars_dir = Path(__file__).parent / "img" / "avatars"
    img_control = None
    avatar_status = ft.Text("", size=10, color=ft.Colors.ON_SURFACE_VARIANT)
    avatar_status.visible = False
    
    # Load default avatar (avatar_default.png - proper PNG format)
    try:
        default_avatar = avatars_dir / "avatar_default.png"
        print(f"[DEBUG] Looking for avatar at: {default_avatar}")
        print(f"[DEBUG] File exists: {default_avatar.exists()}")
        
        if default_avatar.exists():
            # Read file as bytes and encode to base64
            with open(default_avatar, "rb") as f:
                image_data = f.read()
            
            # Create base64 data URI
            b64_string = base64.b64encode(image_data).decode('ascii')
            data_uri = f"data:image/png;base64,{b64_string}"
            
            print(f"[DEBUG] Image size: {len(image_data)} bytes, base64: {len(b64_string)} chars")
            
            img_control = ft.Image(src=data_uri, width=96, height=96)
            avatar_status.value = f"Avatar: {default_avatar.name}"
            print("[OK] Avatar loaded as base64 data URI")
        else:
            # No default avatar found
            print(f"[WARNING] Avatar file not found at {default_avatar}")
            img_control = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.PERSON, size=48, color=ft.Colors.OUTLINE),
                    ft.Text("Avatar non trovato", size=10)
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=4),
                alignment=ft.Alignment(0, 0),
                height=96,
                width=96,
            )
    except Exception as ex:
        # Error loading avatar
        print(f"[ERROR] Avatar exception: {ex}")
        import traceback
        traceback.print_exc()
        img_control = ft.Container(
            content=ft.Text("Errore avatar", size=10),
            alignment=ft.Alignment(0, 0),
            height=96,
            width=96,
        )

    # Add FilePicker and a button to change the image; save copies to img/avatars
    def on_pick_result(e):
        nonlocal img_control
        try:
            if not getattr(e, "files", None):
                return
            picked = e.files[0]
            src_path = Path(getattr(picked, "path", "") or getattr(picked, "name", ""))
            if not src_path.exists():
                # some platforms provide a bytes object in picked.data; try to write it
                data_bytes = getattr(picked, "bytes_data", None) or getattr(picked, "data", None)
                if data_bytes:
                    avatars_dir = Path(__file__).parent / "img" / "avatars"
                    avatars_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Write to temporary file first
                    import tempfile
                    temp_path = Path(tempfile.mktemp(suffix=".tmp"))
                    with open(temp_path, "wb") as f:
                        f.write(data_bytes)
                    
                    dest = avatars_dir / f"avatar_{dm.current_character_id or 'default'}.png"
                    
                    # Validate and convert avatar
                    success, message = validate_and_convert_avatar(temp_path, dest)
                    temp_path.unlink(missing_ok=True)
                    
                    if not success:
                        page.snack_bar = ft.SnackBar(ft.Text(message))
                        page.snack_bar.open = True
                        page.update()
                        return
                    
                    # Load as base64 data URI
                    try:
                        with open(dest, "rb") as f:
                            b = f.read()
                        b64 = base64.b64encode(b).decode("ascii")
                        data_uri = f"data:image/png;base64,{b64}"
                        new_img = ft.Image(src=data_uri, width=96, height=96)
                        new_container = ft.Container(content=new_img, padding=0, alignment=ft.Alignment(0, 0))
                        image_holder.content = new_container
                        img_control = new_container
                        image_holder.update()
                    except Exception:
                        pass
                    dm.data["avatar_path"] = str(dest)
                    dm.do_save()  # Use immediate save instead of scheduled save
                    reload_avatar()  # Force UI refresh after save
                    try:
                        avatar_status.value = message
                        avatar_status.update()
                    except Exception:
                        pass
                    page.update()
                    return
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("File non valido selezionato"))
                    page.snack_bar.open = True
                    page.update()
                    return
                    

            ext = src_path.suffix.lower()
            avatars_dir = Path(__file__).parent / "img" / "avatars"
            avatars_dir.mkdir(parents=True, exist_ok=True)
            dest = avatars_dir / f"avatar_{dm.current_character_id or 'default'}.png"
            
            # Validate and convert avatar (handles all formats)
            success, message = validate_and_convert_avatar(src_path, dest)
            if success:
                # display by embedding image as base64 data URI (avoids file:// issues)
                try:
                    with open(dest, "rb") as f:
                        b = f.read()
                    b64 = base64.b64encode(b).decode("ascii")
                    data_uri = f"data:image/png;base64,{b64}"
                    new_img = ft.Image(src=data_uri, width=96, height=96)
                    new_container = ft.Container(content=new_img, padding=0, alignment=ft.Alignment(0, 0))
                    try:
                        image_holder.content = new_container
                        img_control = new_container
                        image_holder.update()
                    except Exception:
                        img_control = new_container
                except Exception:
                    pass
                dm.data["avatar_path"] = str(dest)
                dm.do_save()  # Use immediate save instead of scheduled save
                reload_avatar()  # Force UI refresh after save
                try:
                    avatar_status.value = message
                    avatar_status.update()
                except Exception:
                    pass
                page.update()
                return
            else:
                # Validation failed
                page.snack_bar = ft.SnackBar(ft.Text(message))
                page.snack_bar.open = True
                page.update()
                return
        except Exception:
            page.snack_bar = ft.SnackBar(ft.Text("Errore durante l'importazione dell'immagine"))
            page.snack_bar.open = True
            page.update()

    # FilePicker is not used to avoid sending unsupported controls to the client.
    # Provide a manual dialog instructing the user to copy an image into img/avatars
    def open_manual_dialog(e):
        avatars_dir = Path(__file__).parent / "img" / "avatars"
        avatars_dir.mkdir(parents=True, exist_ok=True)

        path_field = ft.TextField(label="Percorso locale del file immagine", width=450)

        def use_path_click(ev):
            try:
                src = path_field.value or ""
                src_path = Path(src)
                if not src_path.exists():
                    page.snack_bar = ft.SnackBar(ft.Text("File non trovato: inserisci un percorso valido"))
                    page.snack_bar.open = True
                    page.update()
                    return
                dest = avatars_dir / f"avatar_{dm.current_character_id or 'default'}.png"
                
                # Validate and convert avatar with size constraints
                success, message = validate_and_convert_avatar(src_path, dest)
                
                if not success:
                    page.snack_bar = ft.SnackBar(ft.Text(message))
                    page.snack_bar.open = True
                    page.update()
                    return
                
                # Update data and save to database
                dm.data["avatar_path"] = str(dest)
                dm.do_save()
                
                # Close dialog
                page.dialog.open = False
                
                # Reload avatar
                reload_avatar()
                
                try:
                    page.snack_bar = ft.SnackBar(ft.Text(message))
                    page.snack_bar.open = True
                    page.update()
                except Exception:
                    pass
            except Exception as ex:
                try:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Errore: {ex}"))
                    page.snack_bar.open = True
                    page.update()
                except Exception:
                    pass

        def close_modal(ev=None):
            page.dialog.open = False
            page.update()

        def open_system_file_picker(ev=None):
            # open a native OS file dialog in a background thread, then copy+reload on the UI thread
            import threading
            
            selected_file = [None]  # Use list to share between threads

            def _pick():
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    # Ensure the dialog appears in front
                    root.attributes("-topmost", True)
                    root.update()
                    file_path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.gif")])
                    root.destroy()
                    if file_path:
                        selected_file[0] = file_path
                except Exception as ex:
                    print(f"[FILE_PICKER] Error: {ex}")
                    import traceback
                    traceback.print_exc()

            # Run file picker and wait
            picker_thread = threading.Thread(target=_pick, daemon=True)
            picker_thread.start()
            picker_thread.join(timeout=60)  # Wait up to 60 seconds
            
            if not selected_file[0]:
                return
                
            # Now do UI updates in main thread
            try:
                src_path = Path(selected_file[0])
                if not src_path.exists():
                    page.snack_bar = ft.SnackBar(ft.Text("File non trovato"))
                    page.snack_bar.open = True
                    page.update()
                    return
                
                dest = avatars_dir / f"avatar_{dm.current_character_id or 'default'}.png"
                
                # Validate and convert avatar with size constraints
                success, message = validate_and_convert_avatar(src_path, dest)
                
                if not success:
                    page.snack_bar = ft.SnackBar(ft.Text(message))
                    page.snack_bar.open = True
                    page.update()
                    return
                
                # Update data and save to database
                dm.data["avatar_path"] = str(dest)
                dm.do_save()
                
                # Close dialog
                page.dialog.open = False
                
                # Reload avatar
                reload_avatar()
                
                try:
                    page.snack_bar = ft.SnackBar(ft.Text(message))
                    page.snack_bar.open = True
                    page.update()
                except Exception:
                    pass
            except Exception as ex:
                import traceback
                traceback.print_exc()
                try:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Errore: {ex}"))
                    page.snack_bar.open = True
                    page.update()
                except Exception:
                    pass

        # Use AlertDialog - appears correctly in front
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambia immagine", weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.Text("Incolla qui il percorso completo di un file PNG/JPG presente sul tuo PC, oppure copia manualmente il file in:", max_lines=2),
                    ft.Text(str(avatars_dir), size=11, color=ft.Colors.GREY_400),
                    path_field,
                ],
                spacing=12,
                tight=True,
            ),
            actions=[
                ft.TextButton("Usa questo file", on_click=use_path_click),
                ft.TextButton("Apri file di sistema", on_click=open_system_file_picker),
                ft.TextButton("Ricarica", on_click=lambda ev: reload_avatar(ev)),
                ft.TextButton("Chiudi", on_click=close_modal),
            ],
        )

        page.dialog = dialog
        dialog.open = True
        page.update()

    def change_image_click(e):
        try:
            open_manual_dialog(e)
        except Exception as ex:
            try:
                page.snack_bar = ft.SnackBar(ft.Text(f"Errore aprendo la dialog: {ex}"))
                page.snack_bar.open = True
                page.update()
            except Exception:
                pass

    def open_system_file_picker_global(ev=None):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            # Ensure the dialog appears in front
            root.attributes("-topmost", True)
            root.update()
            file_path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
            root.destroy()
        except Exception:
            file_path = ""
        if not file_path:
            return

        try:
            src_path = Path(file_path)
            if not src_path.exists():
                page.snack_bar = ft.SnackBar(ft.Text("File non trovato"))
                page.snack_bar.open = True
                page.update()
                return
            
            dest = Path(__file__).parent / "img" / "avatars" / f"avatar_{dm.current_character_id or 'default'}.png"
            
            # Validate and convert avatar with size constraints
            success, message = validate_and_convert_avatar(src_path, dest)
            
            if not success:
                page.snack_bar = ft.SnackBar(ft.Text(message))
                page.snack_bar.open = True
                page.update()
                return
            
            # Update data and save
            dm.data["avatar_path"] = str(dest)
            dm.schedule_save()
            
            try:
                avatar_status.value = message
                avatar_status.update()
            except Exception:
                pass
            try:
                page.snack_bar = ft.SnackBar(ft.Text(message))
                page.snack_bar.open = True
            except Exception:
                pass
            reload_avatar()
            try:
                for o in list(page.overlay):
                    try:
                        page.overlay.remove(o)
                    except Exception:
                        pass
            except Exception:
                pass
            page.update()
        except Exception as ex:
            import traceback
            traceback.print_exc()
            try:
                page.snack_bar = ft.SnackBar(ft.Text(f"Errore: {ex}"))
                page.snack_bar.open = True
                page.update()
            except Exception:
                pass

    # Icon button to change avatar
    change_btn = ft.IconButton(
        icon=ft.Icons.IMAGE_OUTLINED,
        tooltip="Cambia immagine",
        on_click=open_system_file_picker_global,
    )

    def validate_and_convert_avatar(src_path: Path, dest_path: Path) -> tuple[bool, str]:
        """
        Validate and convert avatar image with size constraints.
        Returns (success: bool, message: str)
        
        Constraints:
        - Max file size: 5MB
        - Max dimensions: 2048x2048 (auto-resize if larger)
        - Always converts to PNG format
        """
        try:
            from PIL import Image
        except ImportError:
            return False, "Pillow non installato. Esegui: pip install Pillow"
        
        try:
            
            # Check file size (max 5MB)
            file_size = src_path.stat().st_size
            max_size = 5 * 1024 * 1024  # 5MB
            if file_size > max_size:
                return False, f"File troppo grande ({file_size // 1024 // 1024}MB). Max 5MB"
            
            # Open and validate image
            try:
                img = Image.open(src_path)
            except Exception as e:
                return False, f"Formato immagine non valido: {e}"
            
            # Resize to 96x96 (icon size) - stretch to exact size
            width, height = img.size
            needs_resize = width != 96 or height != 96
            
            if needs_resize:
                # Resize to 96x96
                img = img.resize((96, 96), Image.Resampling.LANCZOS)
                print(f"[AVATAR] Resized from {width}x{height} to 96x96")
            
            # Convert to RGB/RGBA for PNG (handles WebP, JPEG, etc.)
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
            
            # Save as PNG
            img.save(dest_path, 'PNG', optimize=True)
            
            final_size = dest_path.stat().st_size
            msg = f"Avatar salvato: 96x96px"
            if needs_resize:
                msg += f" (ridimensionato da {width}x{height})"
            msg += f", {final_size // 1024}KB"
            
            return True, msg
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Errore conversione: {e}"

    image_holder = ft.Container(
        content=img_control,
        width=96,
        height=96,
        alignment=ft.Alignment(0, 0),
    )

    image_inner = ft.Column(
        [
            ft.Row(
                [image_holder, change_btn],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            avatar_status,
        ],
        spacing=6,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    avatar_block = ft.Container(
        content=image_inner,
        padding=8,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        width=170,
        alignment=ft.Alignment(0, 0),
    )

    header_card = ft.Container(
        content=ft.Row(
            [
                avatar_block,
                ft.Column(
                    [
                        ft.Text("Dati Base", size=16, weight=ft.FontWeight.BOLD),
                        ft.Row([nome, xp_block], spacing=12),
                        motivazione,
                    ],
                    expand=True,
                    spacing=12,
                ),
            ],
            alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        width=770,
    )

    def reload_avatar(e=None):
        """Reload avatar image from disk using base64 data URI."""
        nonlocal img_control
        try:
            avatars_dir = Path(__file__).parent / "img" / "avatars"
            dest = avatars_dir / f"avatar_{dm.current_character_id or 'default'}.png"
            print(f"[RELOAD_AVATAR] Looking for: {dest}")
            print(f"[RELOAD_AVATAR] Character ID: {dm.current_character_id}")
            print(f"[RELOAD_AVATAR] File exists: {dest.exists()}")
            
            # Fallback to avatar_default.png if character-specific avatar doesn't exist
            if not dest.exists():
                fallback_dest = avatars_dir / "avatar_default.png"
                if fallback_dest.exists():
                    dest = fallback_dest
                    print(f"[RELOAD_AVATAR] Using fallback: {dest}")
            
            if dest.exists():
                try:
                    # Read file and encode to base64 (same as initial load)
                    with open(dest, "rb") as f:
                        image_data = f.read()
                    b64_string = base64.b64encode(image_data).decode('ascii')
                    data_uri = f"data:image/png;base64,{b64_string}"
                    
                    new_img = ft.Image(src=data_uri, width=96, height=96)
                    new_container = ft.Container(content=new_img, padding=0, alignment=ft.Alignment(0,0))
                    
                    # Update only the image control in image_inner
                    image_holder.content = new_container
                    img_control = new_container
                    image_holder.update()
                    print(f"[RELOAD_AVATAR] Successfully updated with base64 data URI")
                    
                    # show confirmation and update status text
                    try:
                        avatar_status.value = f"Avatar caricato: {dest.name}"
                        avatar_status.update()
                    except Exception:
                        pass
                    try:
                        page.snack_bar = ft.SnackBar(ft.Text(f"Avatar caricato: {dest.name}"))
                        page.snack_bar.open = True
                    except Exception:
                        pass
                except Exception as ex:
                    print(f"[RELOAD_AVATAR] Error: {ex}")
                    import traceback
                    traceback.print_exc()
                page.update()
            else:
                # show visible fallback in UI
                print(f"[RELOAD_AVATAR] Avatar file NOT found at {dest}")
                fb = ft.Container(content=ft.Text("Nessun avatar", size=10), alignment=ft.Alignment(0,0), height=96, width=96)
                try:
                    image_holder.content = fb
                    image_holder.update()
                except Exception:
                    pass
                page.snack_bar = ft.SnackBar(ft.Text("Nessun avatar trovato in img/avatars"))
                page.snack_bar.open = True
                page.update()
        except Exception as ex:
            print(f"[RELOAD_AVATAR] Exception: {ex}")
            import traceback
            traceback.print_exc()
            page.snack_bar = ft.SnackBar(ft.Text("Errore nel caricamento dell'avatar"))
            page.snack_bar.open = True
            page.update()

    money_card = ft.Container(
        content=ft.Column(
            [
                ft.Text("Soldi", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([corone, scellini, rame], spacing=12, wrap=True),
            ],
            spacing=8,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        width=770,
    )

    status_card = ft.Container(
        content=ft.Column(
            [
                ft.Text("Status Negativo", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([adrenalina_switch, confusione_switch, svantaggio_switch, malus], spacing=12),
            ],
            spacing=8,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        width=770,
    )

    inventory_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Inventario", size=16, weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                ft.Button("Aggiungi", icon=ft.Icons.ADD, on_click=add_item),
                                ft.Button(
                                    "Importa dal PDF",
                                    icon=ft.Icons.UPLOAD_FILE,
                                    on_click=import_from_pdf,
                                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                ),
                            ],
                            spacing=8,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(
                    inv_grid,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=10,
                    padding=8,
                    expand=True,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        expand=True,
    )

    qualita_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Qualità", size=16, weight=ft.FontWeight.BOLD),
                        ft.Button("Aggiungi", icon=ft.Icons.ADD, on_click=add_qualita),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(
                    qualita_list,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=10,
                    padding=8,
                    expand=True,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        expand=True,
    )

    imparato_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Cosa ho imparato", size=16, weight=ft.FontWeight.BOLD),
                        ft.Button("Aggiungi", icon=ft.Icons.ADD, on_click=add_imparato),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(
                    imparato_list,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=10,
                    padding=8,
                    expand=True,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        expand=True,
    )

    notes_card = ft.Container(
        content=ft.Column(
            [
                ft.Text("Appunti", size=16, weight=ft.FontWeight.BOLD),
                ft.Container(
                    appunti,
                    padding=12,
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    expand=True,
                ),
            ],
            spacing=8,
            expand=True,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        expand=True,
    )

    # Left column containing header, money and status
    left_column = ft.Column([header_card, money_card, status_card], spacing=16, width=770, tight=True)
    
    scheda_view = ft.Row(
        [
            left_column,
            ft.Column([inventory_card], spacing=16, expand=True, tight=False),
        ],
        spacing=16,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        visible=True,
    )

    appunti_view = ft.Column([notes_card], expand=True, visible=False)
    qualita_view = ft.Column([qualita_card, imparato_card], expand=True, visible=False)

    # Items Library View
    items_library_list = ft.ListView(expand=True, spacing=8, padding=10)
    items_search_field = ft.TextField(
        label="Cerca per nome o effetto",
        prefix_icon=ft.Icons.SEARCH,
        width=300,
    )
    
    def on_items_search_change(e):
        """Aggiorna la lista quando il testo di ricerca cambia"""
        refresh_items_library()
    
    items_search_field.on_change = on_items_search_change

    item_name_edit = ft.TextField(label="Nome", expand=True)

    item_icon_preview = ft.Icon(
        CATEGORY_ICONS.get(CATEGORIES[0], ft.Icons.HELP_OUTLINE),
        size=64,
        color=ft.Colors.PRIMARY,
    )
    item_icon_container = ft.Container(
        content=item_icon_preview,
        alignment=ft.Alignment(0, 0),
        padding=16,
    )

    def update_icon_preview(e=None):
        cat = None
        if e is not None:
            if hasattr(e, "control") and getattr(e.control, "value", None):
                cat = e.control.value
            elif hasattr(e, "data") and e.data:
                cat = e.data
        if not cat:
            cat = item_category_edit.value or CATEGORIES[0]
        new_icon = CATEGORY_ICONS.get(cat, ft.Icons.HELP_OUTLINE)
        item_icon_container.content = ft.Icon(new_icon, size=64, color=ft.Colors.PRIMARY)
        item_icon_container.update()
        page.update()

    item_category_edit = ft.Dropdown(
        label="Categoria",
        options=[ft.dropdown.Option(c) for c in CATEGORIES],
        value=CATEGORIES[0],
    )
    item_category_edit.on_select = update_icon_preview
    item_category_edit.on_blur = update_icon_preview

    item_description_edit = ft.TextField(label="Descrizione", multiline=True, min_lines=2, max_lines=3)
    item_effect_edit = ft.TextField(label="Effetto", multiline=True, min_lines=2, max_lines=3)
    editing_item_id = None

    def on_item_form_change(e=None):
        if editing_item_id is None:
            return
        refresh_items_library()
        page.update()

    item_name_edit.on_change = on_item_form_change
    item_description_edit.on_change = on_item_form_change
    item_effect_edit.on_change = on_item_form_change

    def on_item_category_change(e=None):
        update_icon_preview(e)
        on_item_form_change(e)

    item_category_edit.on_select = on_item_category_change
    item_category_edit.on_blur = on_item_category_change

    items_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Libreria Oggetti", size=16, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        items_search_field,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    spacing=12,
                ),
                ft.Container(
                    items_library_list,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=10,
                    padding=8,
                    expand=True,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        expand=2,
    )

    def refresh_items_library():
        items_library_list.controls.clear()
        items = get_all_items()
        
        # Filtro in base al testo di ricerca
        search_text = items_search_field.value.lower().strip()
        if search_text:
            items = [
                item for item in items
                if search_text in item["name"].lower() or search_text in (item.get("effect") or "").lower()
            ]
        
        for item in items:
            display_name = item.get("name") or ""
            display_desc = item.get("description") or ""
            display_effect = item.get("effect") or ""
            display_category = item.get("category") or CATEGORIES[0]
            if editing_item_id == item.get("id"):
                display_name = (item_name_edit.value or display_name).strip()
                display_desc = item_description_edit.value or ""
                display_effect = item_effect_edit.value or ""
                display_category = item_category_edit.value or display_category

            icon = CATEGORY_ICONS.get(display_category, ft.Icons.HELP_OUTLINE)
            
            # Conte quanti di questo item abbiamo nell'inventario
            item_count = 0
            for inv_item in data.get("inventario", []):
                if isinstance(inv_item, dict) and inv_item.get("item_id") == item["id"]:
                    item_count += inv_item.get("qty", 1)
            
            def on_add_to_inventory(e, i=item):
                if dm.current_character_id is None:
                    page.snack_bar = ft.SnackBar(ft.Text("Carica o crea un personaggio prima"))
                    page.snack_bar.open = True
                    page.update()
                    return
                # Aggiungi l'item all'inventario con nome e item_id
                data["inventario"].append({"item_id": i["id"], "name": i["name"], "qty": 1})
                schedule_save()
                refresh_inventory()
                refresh_items_library()  # Aggiorna il contatore
                page.snack_bar = ft.SnackBar(ft.Text(f"'{i['name']}' aggiunto all'inventario"))
                page.snack_bar.open = True
                page.update()
            
            # Badge con contatore
            counter_badge = ft.Container(
                content=ft.Text(str(item_count), size=10, color=ft.Colors.ON_PRIMARY, weight=ft.FontWeight.BOLD),
                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                border_radius=10,
                bgcolor=ft.Colors.PRIMARY if item_count > 0 else ft.Colors.OUTLINE,
            ) if item_count > 0 else ft.Container()
            
            items_library_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                icon,
                                size=32,
                                color=ft.Colors.PRIMARY,
                                tooltip=f"Categoria: {display_category}",
                            ),
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(display_name, size=14, weight=ft.FontWeight.BOLD),
                                            counter_badge,
                                        ],
                                        spacing=8,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    ft.Text(f"Descrizione: {display_desc}", size=11, max_lines=2) if display_desc else ft.Text("Descrizione: ", size=11),
                                    ft.Text(f"Effetto: {display_effect}", size=11, max_lines=1) if display_effect else None,
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ADD,
                                tooltip="Aggiungi all'inventario",
                                on_click=on_add_to_inventory,
                                icon_color=ft.Colors.GREEN,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                tooltip="Modifica",
                                on_click=lambda e, i=item: edit_item(i),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE,
                                tooltip="Elimina",
                                on_click=lambda e, i=item: delete_item(i),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        spacing=12,
                    ),
                    padding=12,
                    border_radius=8,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                )
            )
        page.update()

    def clear_item_form():
        nonlocal editing_item_id
        editing_item_id = None
        item_name_edit.value = ""
        item_category_edit.value = CATEGORIES[0]
        item_description_edit.value = ""
        item_effect_edit.value = ""
        update_icon_preview()
        page.update()

    def save_item(e):
        nonlocal editing_item_id
        if not item_name_edit.value or not item_category_edit.value:
            return
        if editing_item_id is not None:
            update_item_in_library(
                editing_item_id,
                item_name_edit.value,
                item_category_edit.value,
                item_description_edit.value or "",
                item_effect_edit.value or "",
            )
            refresh_inventory()
        else:
            new_item_id = add_item_to_library(
                item_name_edit.value,
                item_category_edit.value,
                item_description_edit.value or "",
                item_effect_edit.value or "",
            )
            # Add the item to the current character's inventory
            if dm.current_character_id is not None:
                data["inventario"].append({"item_id": new_item_id, "qty": 1})
                schedule_save()
                refresh_inventory()
        clear_item_form()
        refresh_items_library()

    def edit_item(item):
        nonlocal editing_item_id
        editing_item_id = item["id"]
        item_name_edit.value = item["name"]
        item_category_edit.value = item["category"]
        item_description_edit.value = item["description"]
        item_effect_edit.value = item["effect"]
        update_icon_preview()
        page.update()

    def delete_item(item):
        delete_item_from_library(item["id"])
        refresh_items_library()


    

    items_form_card = ft.Container(
        content=ft.Column(
            [
                ft.Text("Aggiungi/Modifica Oggetto", size=16, weight=ft.FontWeight.BOLD),
                item_icon_container,
                item_name_edit,
                item_category_edit,
                item_description_edit,
                item_effect_edit,
                ft.Row(
                    [
                        ft.Button("Salva", icon=ft.Icons.SAVE, on_click=save_item),
                        ft.Button("Annulla", on_click=lambda e: clear_item_form()),
                    ],
                    spacing=8,
                ),
            ],
            spacing=12,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        expand=1,
    )

    items_view = ft.Row(
        [
            items_card,
            items_form_card,
        ],
        spacing=16,
        expand=True,
        visible=False,
    )

    tab_active_bg = ft.Colors.PRIMARY_CONTAINER

    btn_scheda = ft.Button("Scheda", icon=ft.Icons.BADGE, bgcolor=tab_active_bg)
    btn_appunti = ft.Button("Appunti", icon=ft.Icons.NOTES)
    btn_qualita = ft.Button("Qualità e tratti", icon=ft.Icons.STARS)
    btn_items = ft.Button("Item", icon=ft.Icons.CATEGORY)

    def set_view(name: str):
        is_scheda = name == "scheda"
        is_appunti = name == "appunti"
        is_qualita = name == "qualita"
        is_items = name == "items"
        scheda_view.visible = is_scheda
        appunti_view.visible = is_appunti
        qualita_view.visible = is_qualita
        items_view.visible = is_items
        btn_scheda.bgcolor = tab_active_bg if is_scheda else None
        btn_appunti.bgcolor = tab_active_bg if is_appunti else None
        btn_qualita.bgcolor = tab_active_bg if is_qualita else None
        btn_items.bgcolor = tab_active_bg if is_items else None
        if is_items:
            refresh_items_library()
        page.update()

    btn_scheda.on_click = lambda e: set_view("scheda")
    btn_appunti.on_click = lambda e: set_view("appunti")
    btn_qualita.on_click = lambda e: set_view("qualita")
    btn_items.on_click = lambda e: set_view("items")

    character_grid = ft.GridView(
        expand=True,
        max_extent=220,
        child_aspect_ratio=0.85,
        spacing=12,
        run_spacing=12,
        padding=8,
    )
    selector_view = ft.Container(
        content=ft.Column(
            [
                ft.Text("Seleziona un personaggio", size=18, weight=ft.FontWeight.BOLD),
                character_grid,
            ],
            spacing=12,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        visible=True,
        alignment=ft.Alignment(0, -1),
    )

    editor_view = ft.Column(
        [
            ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        tooltip="Torna alla selezione personaggi",
                        on_click=go_back_to_selector,
                    ),
                    ft.IconButton(icon=ft.Icons.SAVE, tooltip="Salva manualmente", on_click=lambda e: do_save()),
                    theme_toggle,
                    ft.Container(expand=True),
                ],
                spacing=8,
            ),
            ft.Row([btn_scheda, btn_appunti, btn_qualita, btn_items], spacing=8),
            scheda_view,
            appunti_view,
            qualita_view,
            items_view,
        ],
        expand=True,
        spacing=12,
        visible=False,
    )

    page.add(
        ft.Column(
            [selector_view, editor_view],
            expand=True,
            spacing=12,
        )
    )
    refresh_character_list()

    # Try to load a default/avatar image immediately (loads avatar_default.png or first PNG found)
    try:
        reload_avatar()
    except Exception:
        pass
