import json
from pathlib import Path

import flet as ft
from pypdf import PdfReader

DATA_FILE = Path(__file__).parent / "personaggio.json"
PDF_FILE = Path(__file__).parent / "scheda.pdf"


def load_data() -> dict:
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        data = {}
    defaults = {
        "nome": "",
        "motivazione": "",
        "inventario_raw": "",
        "xp_raw": "",
        "inventario": [],
        "appunti": "",
    }
    for k, v in defaults.items():
        data.setdefault(k, v)
    return data


def save_data(data: dict) -> None:
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_pdf_fields(pdf_path: Path) -> dict:
    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}
    out = {}
    for k, v in fields.items():
        val = v.get("/V", "")
        if val is None:
            val = ""
        out[k] = str(val)
    return out


def split_inventory_raw(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    # separa gli oggetti dopo ogni "(xN)"
    raw = raw.replace(") ", ")\n")
    parts = [p.strip() for p in raw.splitlines() if p.strip()]
    return parts


def main(page: ft.Page):
    page.title = "Scheda DD"
    page.window_width = 1050
    page.window_height = 720

    data = load_data()

    if (not data.get("inventario")) and data.get("inventario_raw"):
        data["inventario"] = split_inventory_raw(data.get("inventario_raw", ""))
        save_data(data)

    nome = ft.TextField(label="Nome", value=data.get("nome", ""), expand=True)
    motivazione = ft.TextField(
        label="Motivazione",
        value=data.get("motivazione", ""),
        multiline=True,
        min_lines=2,
        max_lines=4,
        expand=True,
    )
    xp = ft.TextField(label="XP", value=data.get("xp_raw", ""), expand=True)
    appunti = ft.TextField(label="Appunti", value=data.get("appunti", ""), multiline=True, expand=True)

    inv_list = ft.ListView(expand=True, spacing=8, padding=10)

    def on_nome_change(e):
        data["nome"] = nome.value
        persist()

    def on_motivazione_change(e):
        data["motivazione"] = motivazione.value
        persist()

    def on_xp_change(e):
        data["xp_raw"] = xp.value
        persist()

    def on_appunti_change(e):
        data["appunti"] = appunti.value
        persist()

    nome.on_change = on_nome_change
    motivazione.on_change = on_motivazione_change
    xp.on_change = on_xp_change
    appunti.on_change = on_appunti_change

    def persist():
        data["nome"] = nome.value
        data["motivazione"] = motivazione.value
        data["xp_raw"] = xp.value
        data["appunti"] = appunti.value
        save_data(data)

    def refresh_inventory():
        inv_list.controls.clear()
        for i, it in enumerate(data.get("inventario", [])):
            txt = ft.TextField(value=it, expand=True)

            def on_change(e, idx=i):
                data["inventario"][idx] = e.control.value
                persist()

            def on_delete(e, idx=i):
                data["inventario"].pop(idx)
                persist()
                refresh_inventory()
                page.update()

            txt.on_change = on_change

            inv_list.controls.append(
                ft.Row(
                    [txt, ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=on_delete)],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

    def add_item(e):
        data.setdefault("inventario", []).append("Nuovo oggetto")
        persist()
        refresh_inventory()
        page.update()

    def import_from_pdf(e=None):
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
        data["inventario"] = split_inventory_raw(data.get("inventario_raw", ""))

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

    # se i campi sono vuoti, prova a importare subito dal PDF
    if (not data.get("nome")) and PDF_FILE.exists():
        import_from_pdf()

    refresh_inventory()

    page.add(
        ft.Column(
            [
                ft.Row([nome, xp]),
                motivazione,
                ft.Divider(),
                ft.Row(
                    [
                        ft.Text("Inventario", size=18, weight=ft.FontWeight.BOLD),
                        ft.Button("Aggiungi", on_click=add_item),
                        ft.Button("Importa dal PDF", on_click=import_from_pdf),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(inv_list, border=ft.border.all(1), border_radius=8, expand=True),
                ft.Divider(),
                appunti,
            ],
            expand=True,
        )
    )


# Flet 0.81: usa run() al posto di app()
ft.run(main)