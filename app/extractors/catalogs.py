from urllib.parse import urlsplit
from urllib.parse import urljoin
import re

from bs4 import BeautifulSoup

from app.extractors.generic import GenericExtractor
from app.schemas import ProductData
from app.utils.money import parse_money
from app.utils.text import clean_text, clean_title
class CatalogExtractor(GenericExtractor):
    domains=(); source_name="catalog"; brand_name=""
    @classmethod
    def supports(cls,url):
        host=(urlsplit(url).hostname or "").lower(); return any(host==d or host.endswith("."+d) for d in cls.domains)
    async def extract(self,url):
        p=await super().extract(url); p.source=self.source_name; p.brand=p.brand or self.brand_name; return p
class IngcoExtractor(CatalogExtractor):
    domains=("ingco.com.uy","ingcouruguay.com","ingcotools.com.uy","web2023.ingcotools.com.uy")
    source_name="ingco"
    brand_name="INGCO"

    async def extract(self,url):
        html,final=await self.fetch(url)
        soup=BeautifulSoup(html,"lxml")
        price_tag=soup.select_one('[itemprop="price"]')
        currency_tag=soup.select_one('[itemprop="priceCurrency"]')
        description_tag=soup.select_one('[itemprop="description"]:not(meta)')
        sku_tag=soup.select_one('[itemprop="sku"]')
        title_tag=soup.select_one('[itemprop="name"]')
        og_title=soup.select_one('meta[property="og:title"]')
        if not title_tag:
            title_tag = soup.select_one("h1.product-title, h1.producto, .producto h1, .product h1, h1")
        title=clean_title(
            (title_tag.get_text(" ",strip=True) if title_tag else "")
            or (og_title.get("content","") if og_title else "")
        )
        # La tienda nueva no siempre publica microdatos: en ese caso el precio,
        # código y título aparecen como texto visible ("Precio USD 12,34",
        # "Ahora USD 12,34", "Cód.ING_ABC123").
        visible_lines = [clean_text(x) for x in soup.get_text("\n").splitlines() if clean_text(x)]
        if not price_tag:
            amount = None
            for line in visible_lines:
                if re.search(r"\bUSD\b", line, re.I) and not re.search(r"\bAntes\b", line, re.I):
                    match = re.search(r"\bUSD\s*([\d.,]+)", line, re.I)
                    if match:
                        amount = match.group(1)
                        break
            if amount:
                price_tag = type("PriceTag", (), {"get": lambda self, key, default=None: amount if key == "content" else default, "get_text": lambda self, *args, **kwargs: amount})()
        if not sku_tag:
            for line in visible_lines:
                match = re.search(r"C[oó]d\.?\s*([A-Za-z0-9_-]{4,})", line, re.I)
                if match:
                    sku_tag = type("SkuTag", (), {"get_text": lambda self, *args, **kwargs: match.group(1)})()
                    break
        if not title:
            result=await super().extract(final)
            result.source=self.source_name
            result.brand=result.brand or self.brand_name
            return result
        description_parts=list(description_tag.stripped_strings) if description_tag else []
        description=clean_text(" ".join(description_parts))
        specifications={}
        included=[]
        in_included=False
        for part in description_parts:
            item=clean_text(part.lstrip("-• "))
            if not item:
                continue
            if item.lower().startswith("incluye"):
                in_included=True
                continue
            if in_included:
                included.append(item)
            elif ":" in item:
                key,value=item.split(":",1)
                if key.strip() and value.strip():
                    specifications[key.strip()]=value.strip()
        breadcrumbs=[x.get_text(" ",strip=True) for x in soup.select('[itemtype$="BreadcrumbList"] [itemprop="name"]')]
        category=breadcrumbs[-1] if breadcrumbs else None
        images=[]
        # En INGCO algunos valores de og:image apuntan a una ruta inexistente que
        # responde con HTML. Las fotos visibles del producto son la fuente más
        # fiable y deben conservarse como imagen principal.
        image_tags = soup.select(
            '.fotos img, .product-images img, img[itemprop="image"], [itemprop="image"] img'
        )
        image_tags.extend(soup.select('meta[property="og:image"]'))
        for tag in image_tags:
            source=tag.get("content") or tag.get("data-src") or tag.get("src")
            if source:
                absolute=urljoin(final,source)
                if absolute not in images:
                    images.append(absolute)
        return ProductData(
            source_url=final,source=self.source_name,title=title,brand=self.brand_name,
            category=category,price=parse_money(price_tag.get("content") or price_tag.get_text("",strip=True)),
            currency=(currency_tag.get("content") if currency_tag else None) or "USD",
            description=description,specifications=specifications,included=included,
            sku=clean_text(sku_tag.get_text(" ",strip=True)) if sku_tag else None,
            images=images,
        )
class EmtopExtractor(CatalogExtractor): domains=("emtop.com","emtop.com.uy"); source_name="emtop"; brand_name="EMTOP"
class WurthExtractor(CatalogExtractor): domains=("wurth.com.uy","wurth.com"); source_name="wurth"; brand_name="Würth"
