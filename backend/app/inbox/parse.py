from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_DECOR = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002700-\U000027bf"
    "\U0001f000-\U0001f0ff"
    "\U0000fe0f"
    "\U0000200d"
    "]+",
    re.UNICODE,
)
_DE_POR = re.compile(
    r"de\s*R?\$?\s*([\d\.\,]+)\s*(?:por|/|\|)\s*(?:por\s*)?R?\$?\s*([\d\.\,]+)",
    re.I,
)
_RS = re.compile(r"R\$\s*([\d\.\,]+)", re.I)
_BARE = re.compile(r"(?:^|[^\d])(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})(?:[^\d]|$)")
_COUPON = re.compile(r"(?:cupom|use o cupom)\s*[:\s]+([A-Z0-9]{4,24})", re.I)
_INSTALLMENT = re.compile(
    r"(?P<n>\d{1,2})\s*x\s*(?:sem\s+juros\s*)?(?:de\s*)?(?:R\$\s*)?(?P<v>[\d\.\,]+)"
    r"|(?:em|ou|parcelad[oa]\s+em)\s+(?P<n2>\d{1,2})\s*x\s*(?:sem\s+juros\s*)?(?:de\s*)?(?:R\$\s*)?(?P<v2>[\d\.\,]+)",
    re.I,
)
_INSTALLMENT_CTX = re.compile(r"(\d{1,2})\s*x|parcela|parcelad|/m[eê]s|por\s+m[eê]s", re.I)
_SKIP_START = (
    "alerta",
    "link",
    "vai abrir",
    "rankiei",
    "outros grupos",
    "torne-se",
    "selecione",
    "conheça",
    "conheca",
    "grupo de",
    "anúncio",
    "anuncio",
    "dica do",
    "top 5",
    "app:",
    "pc:",
)
_PRODUCT_HINT = re.compile(
    r"\b(\d+\s?(ml|mm|gb|tb|w|hz|pol|litros?)|intel|amd|ryzen|rtx|ssd|cooler|teclado|monitor|placa)\b",
    re.I,
)
_SLOGAN = (
    "voltou",
    "e tome",
    "esse não",
    "esse nao",
    "não tem erro",
    "nao tem erro",
    "precinho",
    "tome miojo",
    "torneira de rico",
)


@dataclass
class ParsedDeal:
    title: str
    price: Decimal | None = None
    listed_price: Decimal | None = None
    coupon: str | None = None
    payment_hint: str | None = None
    installment_hint: str | None = None


def parse_deal(text: str | None, *, fallback: str = "Promoção do grupo") -> ParsedDeal:
    raw = text or ""
    count, installment, interest_free = _installment(raw)
    listed, price = _prices(raw, installment_amount=installment)
    coupon = _coupon(raw)
    hint = "Pix" if re.search(r"\bpix\b", raw, re.I) else None
    title = _title(raw, fallback=fallback)
    return ParsedDeal(
        title=title,
        price=price,
        listed_price=listed,
        coupon=coupon,
        payment_hint=hint,
        installment_hint=_installment_label(count, installment, interest_free),
    )


def _money(raw: str) -> Decimal | None:
    token = raw.strip()
    if not token:
        return None
    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        token = token.replace(",", ".")
    elif token.count(".") == 1 and len(token.split(".")[-1]) == 3:
        token = token.replace(".", "")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    if value <= 0 or value > 500_000:
        return None
    return value


def _installment(text: str) -> tuple[int | None, Decimal | None, bool]:
    interest_free = bool(re.search(r"sem\s+juros", text or "", re.I))
    match = _INSTALLMENT.search(text or "")
    if not match:
        return None, None, False
    count = int(match.group("n") or match.group("n2") or 0)
    amount = _money(match.group("v") or match.group("v2") or "")
    if count < 2 or count > 24 or amount is None:
        return None, None, False
    return count, amount, interest_free


def _installment_label(count: int | None, amount: Decimal | None, interest_free: bool) -> str | None:
    if amount is None or not count:
        return None
    quantized = amount.quantize(Decimal("0.01"))
    money = f"R$ {quantized:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    label = f"{count}x de {money}"
    if interest_free:
        label += " sem juros"
    return label


def _is_installment_context(text: str, start: int) -> bool:
    window = text[max(0, start - 36) : start]
    return bool(_INSTALLMENT_CTX.search(window))


def _cash_amounts(text: str, installment_amount: Decimal | None) -> list[Decimal]:
    found: list[Decimal] = []
    for match in _RS.finditer(text):
        if _is_installment_context(text, match.start()):
            continue
        value = _money(match.group(1))
        if value is None:
            continue
        if installment_amount is not None and value == installment_amount:
            continue
        found.append(value)
    if found:
        return _drop_installment_lookalikes(found)
    for match in _BARE.finditer(text):
        if _is_installment_context(text, match.start()):
            continue
        value = _money(match.group(1))
        if value is None:
            continue
        if installment_amount is not None and value == installment_amount:
            continue
        found.append(value)
    return _drop_installment_lookalikes(found)


def _drop_installment_lookalikes(found: list[Decimal]) -> list[Decimal]:
    if len(found) < 2:
        return found
    kept: list[Decimal] = []
    for value in found:
        looks_like_parcel = False
        for other in found:
            if other <= value * Decimal("1.8"):
                continue
            ratio = other / value
            steps = int(ratio.quantize(Decimal("1")))
            if 2 <= steps <= 18 and abs(ratio - steps) < Decimal("0.08"):
                looks_like_parcel = True
                break
        if not looks_like_parcel:
            kept.append(value)
    return kept or found


def _prices(text: str, *, installment_amount: Decimal | None = None) -> tuple[Decimal | None, Decimal | None]:
    match = _DE_POR.search(text)
    if match:
        listed, current = _money(match.group(1)), _money(match.group(2))
        if current and (installment_amount is None or current != installment_amount):
            return listed, current
    found = _cash_amounts(text, installment_amount)
    if not found:
        return None, None
    if len(found) >= 2 and found[0] > found[-1]:
        return found[0], found[-1]
    return None, found[0]


def _coupon(text: str) -> str | None:
    match = _COUPON.search(text or "")
    if not match:
        return None
    return match.group(1).upper()


def _clean_line(line: str) -> str:
    clean = _URL.sub("", line)
    clean = _DECOR.sub("", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" -–|•*:")
    return clean


def _is_skip(line: str) -> bool:
    low = line.lower()
    if len(line) < 8:
        return True
    if low.startswith("é ") or low.startswith("e disparado") or "custo x" in low:
        return True
    if any(low.startswith(prefix) for prefix in _SKIP_START):
        return True
    if _RS.fullmatch(line) or re.fullmatch(r"(de|por)\s+R?\$?\s*[\d\.\,]+.*", low):
        return True
    if "cupom" in low and len(line) < 48:
        return True
    if "link do produto" in low or "link app" in low:
        return True
    return False


def _is_slogan(line: str) -> bool:
    low = line.lower()
    if any(token in low for token in _SLOGAN) and len(line) < 55:
        return True
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", line)
    return bool(letters) and letters.isupper() and len(line) <= 42 and not re.search(r"\d", line)


def _title(text: str, *, fallback: str) -> str:
    lines = [_clean_line(line) for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    candidates = [line for line in lines if not _is_skip(line)]
    hinted = [line for line in candidates if _PRODUCT_HINT.search(line) and not _is_slogan(line)]
    if hinted:
        return hinted[0][:180]
    for line in candidates:
        if not _is_slogan(line):
            return line[:180]
    if candidates:
        return candidates[0][:180]
    return fallback
