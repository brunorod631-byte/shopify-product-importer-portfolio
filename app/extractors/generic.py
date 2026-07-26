import json
import re
from typing import Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app.extractors.base import BaseExtractor, ExtractionError
from app.schemas import ProductData
from app.utils.money import parse_money
from app.utils.text import clean_text, clean_title

GENERIC_SITE_TITLE = re.compile(r"\b(importador|mayorista|distribuidor|inicio|home|cat[aá]logo|bienvenid[oa]|tienda online)\b",re.I)

def best_html_title(soup: BeautifulSoup,meta: dict) -> str:
    metadata=clean_title(meta.get("og:title") or meta.get("twitter:title") or (soup.title.string if soup.title else ""))
    headings=[]
    for selector in ("h1.page-header","h1[itemprop='name']","[itemprop='name'] h1","main h1",".product h1",".producto h1","h1"):
        for element in soup.select(selector):
            value=clean_title(element.get_text(" ",strip=True))
            if value and value.casefold() not in {"productos","producto","catálogo","catalogo"} and value not in headings:
                headings.append(value)
    if headings and (not metadata or GENERIC_SITE_TITLE.search(metadata)):
        return headings[0]
    return metadata or (headings[0] if headings else "")

def _products(value: Any):
    if isinstance(value, list):
        for item in value: yield from _products(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str): types = [types]
        if "Product" in types: yield value
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in value: yield from _products(value[key])

def parse_jsonld(html: str, url: str, source: str = "generic") -> ProductData | None:
    soup = BeautifulSoup(html, "lxml")
    for script in soup.select('script[type="application/ld+json"]'):
        try: blocks = list(_products(json.loads(script.string or "")))
        except (json.JSONDecodeError, TypeError): continue
        for p in blocks:
            offers = p.get("offers") or {}; offers = offers[0] if isinstance(offers, list) and offers else offers
            brand = p.get("brand"); brand = brand.get("name") if isinstance(brand, dict) else brand
            images = p.get("image") or []; images = [images] if isinstance(images, str) else images
            specs = {clean_text(str(x["name"])): clean_text(str(x["value"])) for x in p.get("additionalProperty", []) if isinstance(x, dict) and x.get("name") and x.get("value")}
            title = clean_title(str(p.get("name") or ""))
            if title:
                return ProductData(source_url=url, source=source, title=title, brand=clean_text(str(brand or "")) or None,
                    category=clean_text(str(p.get("category") or "")) or None, price=parse_money(offers.get("price") or offers.get("lowPrice")),
                    compare_at_price=parse_money(offers.get("highPrice")), currency=offers.get("priceCurrency"),
                    description=clean_text(str(p.get("description") or "")), sku=p.get("sku"), mpn=p.get("mpn"),
                    barcode=p.get("gtin13") or p.get("gtin"), availability=offers.get("availability"), specifications=specs,
                    images=[urljoin(url, str(x.get("url") if isinstance(x, dict) else x)) for x in images if x])
    return None

class GenericExtractor(BaseExtractor):
    @classmethod
    def supports(cls, url: str) -> bool: return True
    async def extract(self, url: str) -> ProductData:
        html, final = await self.fetch(url); result = parse_jsonld(html, final)
        if result:
            if not result.images: result.images=await self._rendered_images(final)
            return result
        soup = BeautifulSoup(html, "lxml"); meta = {x.get("property") or x.get("name"): x.get("content") for x in soup.select("meta[content]")}
        title = best_html_title(soup,meta)
        if not title: raise ExtractionError("No se encontró un producto público")
        image = meta.get("og:image")
        product=ProductData(source_url=final, title=title, description=clean_text(meta.get("og:description", "")),
            price=parse_money(meta.get("product:price:amount")), currency=meta.get("product:price:currency"),
            images=[urljoin(final, image)] if image else [], warnings=["Extracción genérica: revise los datos"])
        if not product.images: product.images=await self._rendered_images(final)
        if not product.images: product.warnings.append("No se detectó una foto; use Asignar foto")
        return product

    async def _rendered_images(self,url: str):
        from app.extractors.rendered_images import rendered_image_candidates
        return await rendered_image_candidates(url,self.settings.request_timeout_seconds,self.settings.max_download_bytes,self.settings.max_images_per_product)
