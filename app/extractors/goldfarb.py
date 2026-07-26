import re
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.extractors.base import ExtractionError
from app.extractors.generic import GenericExtractor
from app.schemas import ProductData
from app.utils.text import clean_text, clean_title
from app.utils.urls import validate_public_url


def product_from_payload(data: dict, source_url: str, max_images: int) -> ProductData:
    products = data.get("products") or []
    if not products:
        raise ExtractionError("Goldfarb no devolvió el producto solicitado")
    item = products[0]
    images = []
    for image in item.get("images") or []:
        candidate = image.get("url") if isinstance(image, dict) else image
        if candidate and candidate.startswith("https://") and candidate not in images:
            images.append(candidate)
    brand = item.get("brand") or {}
    description = BeautifulSoup(item.get("description") or "", "lxml").get_text(" ", strip=True)
    amount = item.get("finalPrice")
    price = Decimal(str(amount)) if amount not in (None, "", 0, "0") else None
    availability = item.get("availability") or ("Disponible" if item.get("hasStock") else "Sin stock")
    return ProductData(
        source_url=source_url,
        source="goldfarb",
        title=clean_title(item.get("title") or "Producto Goldfarb"),
        brand=clean_text(brand.get("name") if isinstance(brand, dict) else str(brand)) or None,
        category=clean_text(item.get("category") or item.get("family") or "") or None,
        price=price,
        currency="UYU" if price is not None else None,
        description=clean_text(description),
        sku=str(item.get("itemCode") or item.get("code") or "") or None,
        barcode=str(item.get("codeBars") or "") or None,
        availability=availability,
        images=images[:max_images],
        specifications={"Unidad": str(item.get("unitsPerItem"))} if item.get("unitsPerItem") else {},
        warnings=[] if images else ["Goldfarb no devolvió una imagen; use Asignar foto"],
    )


class GoldfarbExtractor(GenericExtractor):
    @classmethod
    def supports(cls, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return host == "goldfarb.com.uy" or host.endswith(".goldfarb.com.uy")

    async def extract(self, url: str):
        safe = validate_public_url(url)
        match = re.search(r"/shop/products/(\d+)", urlsplit(safe).path, re.I)
        if not match:
            return await super().extract(safe)
        item_code = match.group(1)
        api_url = f"https://www.goldfarb.com.uy/api/products/lookup?itemcodes={item_code}&withDesc=true"
        headers = {
            "User-Agent": "ShopifyTelegramImporter/1.0 (+local merchant importer)",
            "Accept": "application/json",
            "Referer": safe,
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, headers=headers) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()
        product = product_from_payload(data, safe, self.settings.max_images_per_product)
        # Verifica que la imagen principal exista y sea realmente una imagen.
        if product.images:
            try:
                async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                    image = await client.get(str(product.images[0]), headers={"User-Agent": headers["User-Agent"], "Referer": safe, "Accept": "image/*"})
                    image.raise_for_status()
                    valid = image.headers.get("content-type", "").lower().startswith("image/") and len(image.content) <= self.settings.max_download_bytes
                if not valid:
                    product.images = []
                    product.warnings.append("La imagen de Goldfarb no pudo validarse; use Asignar foto")
            except httpx.HTTPError:
                product.images = []
                product.warnings.append("La imagen de Goldfarb no pudo descargarse; use Asignar foto")
        return product
