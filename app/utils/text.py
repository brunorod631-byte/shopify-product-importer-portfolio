import re
import unicodedata

import bleach

BLOCKED = re.compile(
    r"(?i)(whatsapp|tel[eé]fono|env[ií]o|financiaci[oó]n|mercado\s*libre|https?://|cuotas?).*?(?:\n|$)"
)


def clean_text(value: str) -> str:
    value = bleach.clean(value or "", tags=[], strip=True)
    value = BLOCKED.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_title(value: str) -> str:
    value = clean_text(value)
    return re.sub(r"\s*[-|]\s*(mercado libre|oficial|oferta).*", "", value, flags=re.I)[:255]


MODEL_CODE = re.compile(
    r"(?<![\w-])(?=[A-Z][A-Z0-9-]{3,}\b)"
    r"(?=[A-Z0-9-]*\d[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\w-])",
    re.I,
)
TECHNICAL_UNIT = re.compile(r"^\d+(?:[.,]\d+)?(?:V|W|MM|CM|M|KG|G|AH|A)$", re.I)
INTERNAL_SPEC_KEYS = re.compile(r"^(?:c[oó]digo|modelo|sku|mpn|ean|gtin|referencia)$", re.I)


def remove_product_codes(value: str, explicit_codes: list[str | None] | None = None) -> str:
    """Remove model/catalog identifiers from customer-visible text."""
    result = value or ""
    for code in explicit_codes or []:
        if code and len(code.strip()) >= 3:
            result = re.sub(rf"(?<!\w){re.escape(code.strip())}(?!\w)", " ", result, flags=re.I)

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        return token if TECHNICAL_UNIT.fullmatch(token) else " "

    result = MODEL_CODE.sub(replace, result)
    result = re.sub(r"\(\s*\)|\[\s*\]", " ", result)
    return re.sub(r"\s+", " ", result).strip(" -|,")


def visible_specifications(specifications: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in specifications.items()
        if not INTERNAL_SPEC_KEYS.fullmatch(key.strip())
    }


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()
