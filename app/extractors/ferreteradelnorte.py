from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.extractors.base import ExtractionError
from app.extractors.generic import GenericExtractor
from app.schemas import ProductData
from app.utils.text import clean_text, clean_title


@dataclass
class GridProduct:
    product_id: str
    title: str
    sku: str | None
    image: str | None
    url: str


def is_product_grid(url: str) -> bool:
    query=parse_qs(urlsplit(url).query)
    return query.get("p",[""])[0]=="productsGrid"


def product_url(base_url: str, product_id: str) -> str:
    parsed=urlsplit(base_url)
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode({"p":"productPage","producto":product_id}),""))


def parse_grid(html: str,url: str) -> list[GridProduct]:
    soup=BeautifulSoup(html,"lxml");products=[]
    for card in soup.select(".tovar_item"):
        title_tag=card.select_one(".tovar_title")
        wrapper=card.select_one(".tovar_img_wrapper[onclick]")
        if not title_tag or not wrapper: continue
        product_id="".join(x for x in wrapper.get("onclick","") if x.isdigit())
        title=clean_title(title_tag.get_text(" ",strip=True))
        if not product_id or not title: continue
        image_tag=card.select_one(".tovar_img_wrapper img")
        image=urljoin(url,image_tag.get("src")) if image_tag and image_tag.get("src") else None
        sku_tag=card.select_one(".tovar_price")
        products.append(GridProduct(product_id,title,clean_text(sku_tag.get_text()) if sku_tag else None,image,product_url(url,product_id)))
    return products


def parse_product(html: str,url: str) -> ProductData:
    soup=BeautifulSoup(html,"lxml")
    title_tag=soup.select_one(".tovar_view_title")
    title=clean_title(title_tag.get_text(" ",strip=True) if title_tag else "")
    if not title: raise ExtractionError("Ferretera del Norte no expuso el nombre del producto")
    brand_tag=soup.select_one(".tovar_brend")
    sku_tag=soup.select_one(".tovar_article")
    image_tag=soup.select_one("#slider2 img, .tovar_view_fotos img")
    image=urljoin(url,image_tag.get("src")) if image_tag and image_tag.get("src") else None
    description_tag=soup.select_one(".product-description,.tovar_view_description .description")
    return ProductData(
        source_url=url,source="ferreteradelnorte",title=title,
        brand=clean_text(brand_tag.get_text(" ",strip=True)) if brand_tag else None,
        description=clean_text(description_tag.get_text(" ",strip=True)) if description_tag else title,
        sku=clean_text(sku_tag.get_text(" ",strip=True)) if sku_tag else None,
        availability="Disponible" if "En Stock" in soup.get_text(" ",strip=True) else None,
        images=[image] if image else [],
        warnings=[] if image else ["Ferretera del Norte no devolvió una imagen; use Asignar foto"],
    )


class FerreteraDelNorteExtractor(GenericExtractor):
    @classmethod
    def supports(cls,url: str) -> bool:
        host=(urlsplit(url).hostname or "").lower()
        return host=="ferreteradelnorte.com" or host.endswith(".ferreteradelnorte.com")

    async def discover(self,url: str) -> list[GridProduct]:
        html,final=await self.fetch(url)
        return parse_grid(html,final)

    async def extract(self,url: str):
        if is_product_grid(url):
            raise ExtractionError("Este enlace contiene varios productos; seleccione uno")
        html,final=await self.fetch(url)
        return parse_product(html,final)
