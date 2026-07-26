from decimal import Decimal, ROUND_HALF_UP


def parse_money(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace("$", "").replace("UYU", "").replace("ARS", "").strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        text = "".join(parts) if len(parts[-1]) == 3 else text.replace(",", ".")
    return Decimal(text).quantize(Decimal("0.01"))


def apply_markup(price: Decimal, percent: Decimal | float, rounding: Decimal = Decimal("1")) -> Decimal:
    result = price * (Decimal("1") + Decimal(str(percent)) / Decimal("100"))
    return (result / rounding).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * rounding

