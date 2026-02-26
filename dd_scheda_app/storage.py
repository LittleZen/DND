from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .bank import default_money, normalize_money
from .inventory import (
    DEFAULT_CATEGORY,
    format_inventory_item,
    normalize_inventory_items,
    parse_inventory_item,
    split_inventory_raw,
)

DB_FILE = Path(__file__).parent / "personaggio.db"
JSON_FILE = Path(__file__).parent / "personaggio.json"


def _connect():
    return sqlite3.connect(DB_FILE)


def _table_exists(conn, name: str) -> bool:
    cur = conn.cursor()
    row = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def sanitize_items(items: list) -> list:
    """Filter out None, empty strings, and convert to strings"""
    return [str(item).strip() for item in items if item and str(item).strip()]


def _table_columns(conn, name: str) -> list[str]:
    cur = conn.cursor()
    rows = cur.execute(f"PRAGMA table_info({name})").fetchall()
    return [r[1] for r in rows]


def init_db() -> None:
    with _connect() as conn:
        cur = conn.cursor()
        # migrate legacy tables if needed
        if _table_exists(conn, "money"):
            cols = _table_columns(conn, "money")
            if "character_id" not in cols and "id" in cols:
                cur.execute(
                    "ALTER TABLE money RENAME TO money_legacy"
                )
        if _table_exists(conn, "inventory"):
            cols = _table_columns(conn, "inventory")
            if "character_id" not in cols and "item" in cols:
                cur.execute(
                    "ALTER TABLE inventory RENAME TO inventory_legacy"
                )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                motivazione TEXT,
                xp_raw TEXT,
                inventario_raw TEXT,
                appunti TEXT,
                avatar_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Migration: add avatar_path column if missing
        cols = _table_columns(conn, "characters")
        if "avatar_path" not in cols:
            cur.execute("ALTER TABLE characters ADD COLUMN avatar_path TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                item_id INTEGER,
                qty INTEGER DEFAULT 1,
                item TEXT,
                category TEXT,
                FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE,
                FOREIGN KEY(item_id) REFERENCES items_library(id) ON DELETE SET NULL
            )
            """
        )
        # Migration: add item_id and qty columns if missing
        cols = _table_columns(conn, "inventory_items")
        if "item_id" not in cols:
            cur.execute("ALTER TABLE inventory_items ADD COLUMN item_id INTEGER")
        if "qty" not in cols:
            cur.execute("ALTER TABLE inventory_items ADD COLUMN qty INTEGER DEFAULT 1")
        if "category" not in cols:
            cur.execute("ALTER TABLE inventory_items ADD COLUMN category TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS qualities_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                item TEXT NOT NULL,
                FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS learned_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                item TEXT NOT NULL,
                FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS money (
                character_id INTEGER PRIMARY KEY,
                corone INTEGER NOT NULL,
                scellini INTEGER NOT NULL,
                rame INTEGER NOT NULL,
                FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items_library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                effect TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _migrate_from_old_schema(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "character"):
        return
    cur = conn.cursor()
    row = cur.execute(
        "SELECT nome, motivazione, xp_raw, inventario_raw, appunti FROM character WHERE id = 1"
    ).fetchone()
    if row is None:
        return
    nome, motivazione, xp_raw, inventario_raw, appunti = row
    cur.execute(
        "INSERT INTO characters (nome, motivazione, xp_raw, inventario_raw, appunti) VALUES (?, ?, ?, ?, ?)",
        (nome or "", motivazione or "", xp_raw or "", inventario_raw or "", appunti or ""),
    )
    character_id = cur.lastrowid
    if _table_exists(conn, "inventory_legacy"):
        inv_rows = cur.execute("SELECT item FROM inventory_legacy ORDER BY idx ASC").fetchall()
        for idx, (item,) in enumerate(inv_rows):
            cur.execute(
                "INSERT INTO inventory_items (character_id, idx, item, category) VALUES (?, ?, ?, ?)",
                (character_id, idx, item, DEFAULT_CATEGORY),
            )
    if _table_exists(conn, "money_legacy"):
        money_row = cur.execute(
            "SELECT corone, scellini, rame FROM money_legacy WHERE id = 1"
        ).fetchone()
        if money_row:
            cur.execute(
                "INSERT INTO money (character_id, corone, scellini, rame) VALUES (?, ?, ?, ?)",
                (character_id, money_row[0], money_row[1], money_row[2]),
            )
    if _table_exists(conn, "inventory_legacy"):
        cur.execute("DROP TABLE inventory_legacy")
    if _table_exists(conn, "money_legacy"):
        cur.execute("DROP TABLE money_legacy")
    conn.commit()


def _migrate_from_json(conn: sqlite3.Connection) -> None:
    if not JSON_FILE.exists():
        return
    data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    inventario = data.get("inventario")
    if not inventario:
        inventario = split_inventory_raw(data.get("inventario_raw", ""))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO characters (nome, motivazione, xp_raw, inventario_raw, appunti) VALUES (?, ?, ?, ?, ?)",
        (
            data.get("nome", ""),
            data.get("motivazione", ""),
            data.get("xp_raw", ""),
            data.get("inventario_raw", ""),
            data.get("appunti", ""),
        ),
    )
    character_id = cur.lastrowid
    for idx, it in enumerate(normalize_inventory_items(inventario or [])):
        item_str = format_inventory_item(it["name"], it["qty"])
        cur.execute(
            "INSERT INTO inventory_items (character_id, idx, item, category) VALUES (?, ?, ?, ?)",
            (character_id, idx, item_str, it.get("category") or DEFAULT_CATEGORY),
        )
    money = default_money()
    cur.execute(
        "INSERT INTO money (character_id, corone, scellini, rame) VALUES (?, ?, ?, ?)",
        (character_id, money["corone"], money["scellini"], money["rame"]),
    )
    conn.commit()


def ensure_db() -> None:
    init_db()
    with _connect() as conn:
        cur = conn.cursor()
        count = cur.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
        if count == 0:
            _migrate_from_old_schema(conn)
            count = cur.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
        if count == 0:
            _migrate_from_json(conn)


def list_characters() -> list[dict]:
    ensure_db()
    with _connect() as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, nome, created_at FROM characters ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [{"id": r[0], "nome": r[1], "created_at": r[2]} for r in rows]


def create_character(nome: str) -> int:
    init_db()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO characters (nome, motivazione, xp_raw, inventario_raw, appunti) VALUES (?, '', '', '', '')",
            (nome or "Senza nome",),
        )
        character_id = cur.lastrowid
        money = default_money()
        cur.execute(
            "INSERT INTO money (character_id, corone, scellini, rame) VALUES (?, ?, ?, ?)",
            (character_id, money["corone"], money["scellini"], money["rame"]),
        )
        conn.commit()
    return character_id


def load_character(character_id: int) -> dict:
    ensure_db()
    with _connect() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT nome, motivazione, xp_raw, inventario_raw, appunti, avatar_path FROM characters WHERE id = ?",
            (character_id,),
        ).fetchone()
        inv_rows = cur.execute(
            "SELECT item_id, qty, item, category FROM inventory_items WHERE character_id = ? ORDER BY idx ASC",
            (character_id,),
        ).fetchall()
        qualities_rows = cur.execute(
            "SELECT item FROM qualities_items WHERE character_id = ? ORDER BY idx ASC",
            (character_id,),
        ).fetchall()
        learned_rows = cur.execute(
            "SELECT item FROM learned_items WHERE character_id = ? ORDER BY idx ASC",
            (character_id,),
        ).fetchall()
        money_row = cur.execute(
            "SELECT corone, scellini, rame FROM money WHERE character_id = ?",
            (character_id,),
        ).fetchone()
    if row is None:
        return {
            "nome": "",
            "motivazione": "",
            "xp_raw": "",
            "inventario_raw": "",
            "inventario": [],
            "qualita": [],
            "imparato": [],
            "appunti": "",
            "money": default_money(),
            "avatar_path": "",
        }
    nome, motivazione, xp_raw, inventario_raw, appunti, avatar_path = row
    inventario = []
    for item_id, qty, item_str, category in inv_rows:
        if item_id:
            # New format: linked to library
            inventario.append({"item_id": item_id, "qty": qty or 1})
        else:
            # Legacy format: parse from string
            name, parsed_qty = parse_inventory_item(item_str)
            inventario.append({
                "item_id": None,
                "name": name,
                "qty": qty or parsed_qty,
                "category": (category or DEFAULT_CATEGORY),
            })
    qualita = [r[0] for r in qualities_rows]
    imparato = [r[0] for r in learned_rows]
    money = default_money()
    if money_row:
        money = {
            "corone": money_row[0],
            "scellini": money_row[1],
            "rame": money_row[2],
        }
    return {
        "nome": nome,
        "motivazione": motivazione,
        "xp_raw": xp_raw,
        "inventario_raw": inventario_raw,
        "inventario": inventario,
        "qualita": qualita,
        "imparato": imparato,
        "appunti": appunti,
        "money": money,
        "avatar_path": avatar_path or "",
    }


def save_character(character_id: int, data: dict) -> None:
    init_db()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE characters
            SET nome = ?, motivazione = ?, xp_raw = ?, inventario_raw = ?, appunti = ?, avatar_path = ?
            WHERE id = ?
            """,
            (
                data.get("nome", ""),
                data.get("motivazione", ""),
                data.get("xp_raw", ""),
                data.get("inventario_raw", ""),
                data.get("appunti", ""),
                data.get("avatar_path", ""),
                character_id,
            ),
        )
        cur.execute("DELETE FROM inventory_items WHERE character_id = ?", (character_id,))
        for idx, it in enumerate(data.get("inventario", [])):
            if isinstance(it, dict) and "item_id" in it and it["item_id"]:
                # New format: linked to library
                item_name = it.get("name", "")  # Ottieni il nome dal dizionario
                cur.execute(
                    "INSERT INTO inventory_items (character_id, idx, item_id, qty, item) VALUES (?, ?, ?, ?, ?)",
                    (character_id, idx, it["item_id"], it.get("qty", 1), item_name),
                )
            else:
                # Legacy format: store as string
                normalized = normalize_inventory_items([it])[0]
                item_str = format_inventory_item(normalized["name"], normalized["qty"])
                cur.execute(
                    "INSERT INTO inventory_items (character_id, idx, item, category, qty) VALUES (?, ?, ?, ?, ?)",
                    (character_id, idx, item_str, normalized.get("category") or DEFAULT_CATEGORY, normalized["qty"]),
                )
        cur.execute("DELETE FROM qualities_items WHERE character_id = ?", (character_id,))
        for idx, item in enumerate(sanitize_items(data.get("qualita", []))):
            cur.execute(
                "INSERT INTO qualities_items (character_id, idx, item) VALUES (?, ?, ?)",
                (character_id, idx, item),
            )
        cur.execute("DELETE FROM learned_items WHERE character_id = ?", (character_id,))
        for idx, item in enumerate(sanitize_items(data.get("imparato", []))):
            cur.execute(
                "INSERT INTO learned_items (character_id, idx, item) VALUES (?, ?, ?)",
                (character_id, idx, item),
            )
        money = normalize_money(data.get("money", {}))
        cur.execute(
            "UPDATE money SET corone = ?, scellini = ?, rame = ? WHERE character_id = ?",
            (money["corone"], money["scellini"], money["rame"], character_id),
        )
        conn.commit()


# Items Library Management

def get_all_items() -> list[dict]:
    """Get all items from the library"""
    with _connect() as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, name, category, description, effect FROM items_library ORDER BY category, name"
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "description": row[3] or "",
                "effect": row[4] or "",
            }
            for row in rows
        ]


def add_item_to_library(name: str, category: str, description: str = "", effect: str = "") -> int:
    """Add a new item to the library"""
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items_library (name, category, description, effect) VALUES (?, ?, ?, ?)",
            (name, category, description, effect),
        )
        conn.commit()
        return cur.lastrowid


def update_item_in_library(item_id: int, name: str, category: str, description: str = "", effect: str = "") -> None:
    """Update an existing item in the library"""
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE items_library SET name = ?, category = ?, description = ?, effect = ? WHERE id = ?",
            (name, category, description, effect, item_id),
        )
        conn.commit()


def delete_item_from_library(item_id: int) -> None:
    """Delete an item from the library"""
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM items_library WHERE id = ?", (item_id,))
        conn.commit()


def get_items_by_category(category: str) -> list[dict]:
    """Get all items of a specific category"""
    with _connect() as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, name, category, description, effect FROM items_library WHERE category = ? ORDER BY name",
            (category,)
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "description": row[3] or "",
                "effect": row[4] or "",
            }
            for row in rows
        ]


def get_item_by_id(item_id: int) -> dict | None:
    """Get a single item from the library by id"""
    with _connect() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, name, category, description, effect FROM items_library WHERE id = ?",
            (item_id,)
        ).fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "description": row[3] or "",
                "effect": row[4] or "",
            }
        return None
