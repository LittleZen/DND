from __future__ import annotations


def to_int(value) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


def default_money() -> dict:
    return {
        "corone": 0,
        "scellini": 0,
        "rame": 0,
    }


def normalize_money(money: dict) -> dict:
    base = default_money()
    if not money:
        return base
    base["corone"] = to_int(money.get("corone"))
    base["scellini"] = to_int(money.get("scellini"))
    base["rame"] = to_int(money.get("rame"))
    return base
