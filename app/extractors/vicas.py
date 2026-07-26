import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.extractors.base import ExtractionError
from app.extractors.generic import GenericExtractor
from app.schemas import ProductData
from app.utils.text import clean_text, clean_title


def parse_vicas_html(html: str, url: str) -> ProductData:
    soup=BeautifulSoup(html,"lxml")
    heading=soup.select_one("h1.page-header")
    title=clean_title(heading.get_text(" ",strip=True) if heading else "")
    if not title or title.casefold()=="productos":
        raise ExtractionError("Vicas no expuso el nombre del producto")
    image_tag=soup.select_one(".carousel-inner .item.active img, .product-detail img, img[itemprop='image']")
    image=urljoin(url,image_tag.get("src") or image_tag.get("data-src")) if image_tag else None
    description=""
    if heading and heading.parent:
        parts=[]
        for element in heading.parent.select("p,div"):
            if element.select_one("a,button"): continue
            value=clean_text(element.get_text(" ",strip=True))
            if value and value != title and value not in parts: parts.append(value)
        description=" ".join(parts)
    brand_match=re.search(r"-\s*([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ0-9 ]{1,24})$",title)
    return ProductData(
        source_url=url,source="vicas",title=title,
        brand=brand_match.group(1).strip().title() if brand_match else None,
        description=description,images=[image] if image else [],
        warnings=[] if image else ["Vicas no devolvió una imagen; use Asignar foto"],
    )


class VicasExtractor(GenericExtractor):
    @classmethod
    def supports(cls,url: str) -> bool:
        host=(urlsplit(url).hostname or "").lower()
        return host=="vicas.com.uy" or host.endswith(".vicas.com.uy")

    async def extract(self,url: str):
        html,final=await self.fetch(url)
        return parse_vicas_html(html,final)
