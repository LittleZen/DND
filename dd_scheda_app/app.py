from pathlib import Path
import re
import sys
import threading

sys.path.append(str(Path(__file__).parent))

import flet as ft
from bank import normalize_money, to_int
from inventory import (
    DEFAULT_CATEGORY,
    format_inventory_item,
    normalize_inventory_items,
    parse_inventory_item,
    split_inventory_raw,
)
from pdf_import import read_pdf_fields
from settings import load_settings, save_settings
from storage import (
    add_item_to_library,
    create_character,
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
    page.window_width = 1050
    page.window_height = 720
    page.padding = 24
    page.bgcolor = ft.Colors.SURFACE
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    settings = load_settings()
    theme_mode_setting = (settings.get("theme_mode") or "dark").lower()
    page.theme_mode = ft.ThemeMode.DARK if theme_mode_setting == "dark" else ft.ThemeMode.LIGHT

    # Application state
    current_character_id = None
    data = {
        "inventario": [],
        "money": {"corone": 0, "scellini": 0, "rame": 0},
        "qualita": [],
        "imparato": [],
        "inventario_raw": "",
        "appunti": "",
        "xp_raw": "",
    }
    save_timer_holder = {"timer": None}

    def do_save():
        if current_character_id is None:
            return
        try:
            save_character(current_character_id, data)
        except Exception:
            pass

    def schedule_save():
        # debounce saves using a Timer stored in save_timer_holder
        try:
            if save_timer_holder.get("timer"):
                try:
                    save_timer_holder["timer"].cancel()
                except Exception:
                    pass
            t = threading.Timer(0.5, do_save)
            t.daemon = True
            save_timer_holder["timer"] = t
            t.start()
        except Exception:
            # fallback: immediate save
            do_save()

    # Basic UI fields that some handlers expect
    nome = ft.TextField(label="Nome", value=data.get("nome", ""), expand=True)
    motivazione = ft.TextField(label="Motivazione", value=data.get("motivazione", ""), expand=True)
    xp = ft.TextField(label="XP", value=data.get("xp_raw", ""), width=100)
    xp_block = ft.Row([xp], spacing=6)

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
    corone = ft.TextField(
        label="Corone",
        value=str(data.get("money", {}).get("corone", 0)),
        prefix_icon=ft.Icons.PAID,
        width=140,
    )
    scellini = ft.TextField(
        label="Scellini",
        value=str(data.get("money", {}).get("scellini", 0)),
        prefix_icon=ft.Icons.MONETIZATION_ON,
        width=140,
    )
    rame = ft.TextField(
        label="Rame",
        value=str(data.get("money", {}).get("rame", 0)),
        prefix_icon=ft.Icons.CURRENCY_BITCOIN,
        width=140,
    )

    inv_grid = ft.GridView(
        expand=True,
        runs_count=3,
        max_extent=250,
        child_aspect_ratio=1.0,
        spacing=12,
        run_spacing=12,
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
        persist()

    def on_motivazione_change(e):
        data["motivazione"] = motivazione.value
        persist()

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
        xp.value = f"{pct}%"
        data["xp_raw"] = xp.value
        update_xp_background()
        persist()

        save_timer = threading.Timer(0.4, do_save)
        save_timer.daemon = True
        save_timer.start()

    def persist():
        if current_character_id is None:
            return
        data["nome"] = nome.value
        data["motivazione"] = motivazione.value
        data["xp_raw"] = xp.value
        data["appunti"] = appunti.value
        data["money"]["corone"] = to_int(corone.value)
        data["money"]["scellini"] = to_int(scellini.value)
        data["money"]["rame"] = to_int(rame.value)
        schedule_save()

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

            qty_field = ft.TextField(value=str(qty_val), width=56, text_align=ft.TextAlign.CENTER)

            def on_inc(e, i=idx):
                try:
                    data["inventario"][i]["qty"] = int(data["inventario"][i].get("qty", 1)) + 1
                except Exception:
                    # fallback: if raw string, parse and replace
                    name, q = parse_inventory_item(str(data["inventario"][i]))
                    data["inventario"][i] = {"name": name, "qty": q + 1, "category": DEFAULT_CATEGORY}
                persist()
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
                persist()
                refresh_inventory()
                page.update()

            def on_delete(e, i=idx):
                try:
                    data["inventario"].pop(i)
                except Exception:
                    pass
                persist()
                refresh_inventory()
                page.update()

            qty_field.on_change = lambda e, i=idx: (
                data["inventario"].__setitem__(i, {**(data.get("inventario")[i] if isinstance(data.get("inventario")[i], dict) else {}), "name": item_name, "qty": int(e.control.value or 1)}) or persist()
            )

            card = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(width=12),
                        ft.Column(
                            [
                                ft.Container(expand=True),
                                ft.Icon(icon, size=44, color=ft.Colors.PRIMARY),
                                ft.Text(item_name, size=14, weight=ft.FontWeight.BOLD, max_lines=2),
                                ft.Container(height=6),
                                ft.Row(
                                    [
                                        ft.IconButton(ft.Icons.REMOVE, on_click=on_dec, icon_size=16),
                                        qty_field,
                                        ft.IconButton(ft.Icons.ADD, on_click=on_inc, icon_size=16),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=6,
                                ),
                                ft.Container(expand=True),
                            ],
                            expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=6,
                        ),
                        ft.Container(
                            content=ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                on_click=on_delete,
                                icon_size=16,
                                icon_color=ft.Colors.ERROR,
                                tooltip="Elimina",
                            ),
                            width=28,
                            alignment=ft.Alignment(1, -1),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=ft.padding.only(left=8, top=4, right=4, bottom=10),
                border_radius=12,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                tooltip=item_effect if item_effect else None,
            )

            inv_grid.controls.append(card)

    def refresh_imparato():
        imparato_list.controls.clear()
        for i, it in enumerate(data.get("imparato", [])):
            txt = ft.TextField(value=it, expand=True)

            def on_change(e, idx=i):
                data["imparato"][idx] = e.control.value
                persist()

            def on_delete(e, idx=i):
                data["imparato"].pop(idx)
                persist()
                refresh_imparato()
                page.update()

            txt.on_change = on_change

            imparato_list.controls.append(
                ft.Row(
                    [txt, ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=on_delete)],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

    def add_item(e):
        # Switch to Item tab to create a new item
        set_view("items")

    def import_from_pdf(e=None):
        if current_character_id is None:
            page.snack_bar = ft.SnackBar(ft.Text("Seleziona o crea un personaggio prima di importare"))
            page.snack_bar.open = True
            page.update()
            return
        if not PDF_FILE.exists():
            page.snack_bar = ft.SnackBar(ft.Text(f"Non trovo {PDF_FILE.name} nella cartella progetto"))
            page.snack_bar.open = True
            page.update()
            return

        fields = read_pdf_fields(PDF_FILE)

        # Campi del tuo PDF: untitled1/2/26/27 :contentReference[oaicite:1]{index=1}
        data["nome"] = fields.get("untitled1", "")
        data["motivazione"] = fields.get("untitled2", "")
        data["inventario_raw"] = fields.get("untitled26", "")
        data["xp_raw"] = fields.get("untitled27", "")

        # inventario strutturato
        data["inventario"] = normalize_inventory_items(
            split_inventory_raw(data.get("inventario_raw", ""))
        )

        # aggiorna UI
        nome.value = data["nome"]
        motivazione.value = data["motivazione"]
        xp.value = data["xp_raw"]
        appunti.value = data["appunti"]

        persist()
        refresh_inventory()

        page.snack_bar = ft.SnackBar(ft.Text("Import completato dal PDF ✅"))
        page.snack_bar.open = True
        page.update()

    refresh_inventory()

    def add_qualita(e):
        data.setdefault("qualita", []).append("Nuova qualità")
        persist()
        refresh_qualita()
        page.update()

    def add_imparato(e):
        data.setdefault("imparato", []).append("Nuova conoscenza")
        persist()
        refresh_imparato()
        page.update()

    def refresh_qualita():
        qualita_list.controls.clear()
        for i, it in enumerate(data.get("qualita", [])):
            txt = ft.TextField(value=it, expand=True)

            def on_change(e, idx=i):
                data["qualita"][idx] = e.control.value
                persist()

            def on_delete(e, idx=i):
                try:
                    data["qualita"].pop(idx)
                except Exception:
                    pass
                persist()
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
        money = normalize_money(data.get("money", {}))
        corone.value = str(money.get("corone", 0))
        scellini.value = str(money.get("scellini", 0))
        rame.value = str(money.get("rame", 0))
        update_xp_background()
        refresh_inventory()
        refresh_qualita()
        refresh_imparato()

    def load_character_by_id(character_id: int):
        nonlocal current_character_id, data
        current_character_id = character_id
        data = load_character(character_id)
        data["money"] = normalize_money(data.get("money", {}))
        data.setdefault("qualita", [])
        apply_data_to_fields()
        selector_view.visible = False
        editor_view.visible = True
        page.update()

    def refresh_character_list():
        character_list.controls.clear()
        characters = list_characters()
        if not characters:
            character_list.controls.append(
                ft.Text("Nessun personaggio trovato. Creane uno nuovo!", italic=True)
            )
        for ch in characters:
            row = ft.Row(
                [
                    ft.Text(ch["nome"], weight=ft.FontWeight.BOLD),
                    ft.Text(f"ID {ch['id']}", color=ft.Colors.OUTLINE),
                    ft.Button(
                        "Apri",
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda e, cid=ch["id"]: load_character_by_id(cid),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            character_list.controls.append(
                ft.Container(
                    content=ft.GestureDetector(
                        content=row,
                        on_double_tap=lambda e, cid=ch["id"]: load_character_by_id(cid),
                    ),
                    padding=8,
                )
            )

    def create_new_character(e):
        name = (new_character_name.value or "").strip() or "Senza nome"
        character_id = create_character(name)
        new_character_name.value = ""
        refresh_character_list()
        load_character_by_id(character_id)

    header_card = ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Dati Base", size=16, weight=ft.FontWeight.BOLD),
                        ft.Row([nome, xp_block], spacing=12),
                        motivazione,
                    ],
                    expand=True,
                    spacing=12,
                )
            ]
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )

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

    scheda_view = ft.Row(
        [
            ft.Column([header_card, money_card], spacing=16, expand=True),
            ft.Column([inventory_card], spacing=16, expand=True),
        ],
        spacing=16,
        expand=True,
        visible=True,
    )

    appunti_view = ft.Column([notes_card], expand=True, visible=False)
    qualita_view = ft.Column([qualita_card, imparato_card], expand=True, visible=False)

    # Items Library View
    items_library_list = ft.ListView(expand=True, spacing=8, padding=10)
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

    def refresh_items_library():
        items_library_list.controls.clear()
        items = get_all_items()
        for item in items:
            icon = CATEGORY_ICONS.get(item["category"], ft.Icons.HELP_OUTLINE)
            items_library_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(icon, size=32, color=ft.Colors.PRIMARY),
                            ft.Column(
                                [
                                    ft.Text(item["name"], size=14, weight=ft.FontWeight.BOLD),
                                    ft.Text(item["category"], size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ft.Text(item["description"], size=11, max_lines=1) if item["description"] else None,
                                ],
                                spacing=2,
                                expand=True,
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
            if current_character_id is not None:
                data["inventario"].append({"item_id": new_item_id, "qty": 1})
                persist()
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

    items_card = ft.Container(
        content=ft.Column(
            [
                ft.Text("Libreria Oggetti", size=16, weight=ft.FontWeight.BOLD),
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

    character_list = ft.ListView(expand=True, spacing=6, padding=8)
    new_character_name = ft.TextField(label="Nuovo personaggio", expand=True)

    selector_view = ft.Container(
        content=ft.Column(
            [
                ft.Text("Seleziona un personaggio", size=18, weight=ft.FontWeight.BOLD),
                character_list,
                ft.Row(
                    [
                        new_character_name,
                        ft.Button("Crea", icon=ft.Icons.ADD, on_click=create_new_character),
                    ],
                    spacing=8,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        visible=True,
    )

    editor_view = ft.Column(
        [
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


# Flet 0.81: usa run() al posto di app()
ft.run(main)