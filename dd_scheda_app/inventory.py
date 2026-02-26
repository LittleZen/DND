from __future__ import annotations

import re

DEFAULT_CATEGORY = "materiale"


def split_inventory_raw(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    # separa gli oggetti dopo ogni "(xN)"
    raw = raw.replace(") ", ")\n")
    parts = [p.strip() for p in raw.splitlines() if p.strip()]
    return parts


def sanitize_items(items: list[str]) -> list[str]:
    return [i.strip() for i in items if i and i.strip()]


def parse_inventory_item(text: str) -> tuple[str, int]:
    text = text or ""
    match = re.match(r"^\s*(.*?)(?:\s*\(x(\d+)\))?\s*$", text)
    name = (match.group(1) if match else text).strip()
    qty = 1
    if match and match.group(2):
        try:
            qty = int(match.group(2))
        except ValueError:
            qty = 1
    if qty < 1:
        qty = 1
    return name, qty


def format_inventory_item(name: str, qty: int) -> str:
    name = (name or "").strip()
    qty = max(1, int(qty))
    if not name:
        return f"(x{qty})"
    return f"{name} (x{qty})"


def normalize_inventory_items(items) -> list[dict]:
    normalized: list[dict] = []
    if not items:
        return normalized
    for it in items:
        if isinstance(it, dict):
            name = (it.get("name") or it.get("item") or "").strip()
            qty = it.get("qty") or it.get("quantity") or 1
            category = (it.get("category") or DEFAULT_CATEGORY).strip()
            normalized.append({"name": name, "qty": max(1, int(qty)), "category": category})
        else:
            name, qty = parse_inventory_item(str(it))
            normalized.append({"name": name, "qty": qty, "category": DEFAULT_CATEGORY})
    return normalized
