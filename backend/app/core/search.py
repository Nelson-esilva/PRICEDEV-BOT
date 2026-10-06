from __future__ import annotations

from sqlalchemy import String, cast, or_

CATEGORY_KEYS: dict[str, list[str]] = {
    "eletronicos": [
        "fone",
        "headphone",
        "monitor",
        "ssd",
        "tv",
        "celular",
        "bluetooth",
        "notebook",
        "caixa som",
    ],
    "casa": ["cafeteira", "air fryer", "geladeira", "panela", "casa", "espresso"],
    "moda": ["tênis", "tenis", "camisa", "nike", "roupa", "calça"],
    "beleza": ["creme", "sérum", "serum", "shampoo", "refil", "desodorante", "gel"],
    "games": ["game", "playstation", "xbox", "nintendo"],
}

STORE_NEEDLES: dict[str, list[str]] = {
    "amazon": ["amazon"],
    "mercadolivre": ["mercado"],
    "shopee": ["shopee"],
    "magalu": ["magalu", "magazine"],
    "kabum": ["kabum"],
    "netshoes": ["netshoes"],
}


def needle(raw: str | None) -> str | None:
    text = "".join(ch for ch in (raw or "").strip()[:80] if ch not in "%_")
    return text or None


def contains(column, raw: str | None):
    text = needle(raw)
    if text is None or column is None:
        return None
    return column.ilike(f"%{text}%")


def any_contains(columns: list, raw: str | None):
    text = needle(raw)
    if text is None:
        return None
    parts = [col.ilike(f"%{text}%") for col in columns if col is not None]
    return or_(*parts) if parts else None


def category_match(product_name, *, category: str | None, category_col=None, reasons_col=None):
    if not category:
        return None
    keys = CATEGORY_KEYS.get(category)
    if keys:
        return or_(*(product_name.ilike(f"%{key}%") for key in keys))
    parts = []
    if category_col is not None:
        parts.append(category_col == category)
    if reasons_col is not None:
        parts.append(cast(reasons_col, String).ilike(f"%hub_cat:{category}%"))
    return or_(*parts) if parts else None


def store_match(store: str | None, *, merchant=None, source=None, urls: list | None = None):
    if not store:
        return None
    needles = STORE_NEEDLES.get(store) or [store]
    parts = []
    for text in needles:
        like = f"%{text}%"
        if merchant is not None:
            parts.append(merchant.ilike(like))
        if source is not None:
            parts.append(source.ilike(like))
        for col in urls or []:
            parts.append(col.ilike(like))
    return or_(*parts) if parts else None


def reason_match(reasons_col, tag: str | None):
    text = needle(tag)
    if text is None:
        return None
    return cast(reasons_col, String).ilike(f"%{text}%")
