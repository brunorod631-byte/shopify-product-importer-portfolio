import re
from decimal import Decimal
from urllib.parse import unquote, urlsplit

from playwright.async_api import async_playwright

from app.extractors.generic import GenericExtractor, parse_jsonld
from app.extractors.base import ExtractionError
from app.schemas import ProductData
from app.utils.text import clean_text, clean_title

class MercadoLibreExtractor(GenericExtractor):
    @classmethod
    def supports(cls, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return "mercadolibre.com" in host or host == "meli.la"
    async def extract(self, url: str):
        html, final = await self.fetch(url)
        structured=parse_jsonld(html, final, "mercadolibre")
        if structured and self._usable_structured(structured):
            return structured
        if structured:
            return await self._extract_rendered(url)
        try:
            return await super().extract(final)
        except ExtractionError:
            return await self._extract_rendered(url)

    @staticmethod
    def _usable_structured(product: ProductData) -> bool:
        return len(product.title.strip()) >= 10 and bool(
            product.price
            or product.images
            or product.description
            or product.specifications
        )

    async def _extract_rendered(self,url: str) -> ProductData:
        allowed=("mercadolibre.com.uy","mercadolibre.com.ar","mercadolibre.com",
                 "mlstatic.com","mercadopago.com","melidata.com","meli.com")
        async with async_playwright() as playwright:
            browser=await playwright.chromium.launch(headless=True)
            context=await browser.new_context(
                user_agent="ShopifyTelegramImporter/1.0 (+local merchant importer)",locale="es-UY"
            )

            async def restrict(route):
                host=(urlsplit(route.request.url).hostname or "").lower()
                safe=route.request.url.startswith("https://") and any(
                    host==domain or host.endswith("."+domain) for domain in allowed
                )
                await (route.continue_() if safe else route.abort())

            await context.route("**/*",restrict)
            page=await context.new_page()
            response=await page.goto(url,wait_until="domcontentloaded",timeout=30_000)
            try:
                await page.locator(
                    ".ui-pdp-price__second-line .andes-money-amount__fraction"
                ).first.wait_for(state="visible",timeout=10_000)
            except Exception:
                pass
            body=await page.locator("body").inner_text()
            if not response or response.status>=400:
                await browser.close()
                raise ExtractionError("Mercado Libre rechazó la carga pública")
            if re.search(r"captcha|verifica que eres|no soy un robot",body,re.I):
                await browser.close()
                raise ExtractionError("Mercado Libre requiere CAPTCHA; use carga manual")
            title_loc=page.locator("h1").first
            price_loc=page.locator(".ui-pdp-price__second-line .andes-money-amount__fraction").first
            if await title_loc.count():
                title=clean_title(await title_loc.inner_text())
            else:
                title=""
            if len(title)<10:
                parts=[part for part in urlsplit(url).path.split("/") if part]
                slug=parts[0] if parts else "Producto de Mercado Libre"
                title=clean_title(unquote(slug).replace("-"," ").title())
            fraction=re.sub(r"\D","",await price_loc.inner_text()) if await price_loc.count() else ""
            cents_loc=page.locator(".ui-pdp-price__second-line .andes-money-amount__cents").first
            cents=re.sub(r"\D","",await cents_loc.inner_text()) if await cents_loc.count() else "00"
            price=Decimal(f"{fraction}.{cents[:2].ljust(2,'0')}") if fraction else None
            host=urlsplit(url).hostname or ""
            currency="ARS" if host.endswith(".com.ar") else "UYU"
            specifications={}
            for row in await page.locator(".ui-pdp-specs__table tr").all():
                cells=await row.locator("th,td").all_inner_texts()
                if len(cells)>=2 and clean_text(cells[0]) and clean_text(cells[1]):
                    specifications[clean_text(cells[0])]=clean_text(cells[1])
            brand=next((value for key,value in specifications.items() if key.lower()=="marca"),None)
            images=[]
            for locator in await page.locator('meta[property="og:image"], figure img').all():
                source=await locator.get_attribute("content") or await locator.get_attribute("data-zoom") or await locator.get_attribute("src")
                if source and source.startswith("https://") and source not in images:
                    images.append(source)
            match=re.search(r"(?:item_id%3A|item_id:|/)(ML[UA]-?\d+)",url,re.I)
            listing_id=match.group(1).replace("-","").upper() if match else None
            await browser.close()
            warnings=["Datos obtenidos de la página pública renderizada; revise antes de confirmar"]
            if price is None:
                warnings.append("Mercado Libre no expuso el precio; use Editar precio e ingrese UYU")
            return ProductData(
                source_url=url,source="mercadolibre",title=title,brand=brand,
                price=price,currency=currency,specifications=specifications,
                sku=listing_id,availability="Disponible" if "stock" in body.lower() else None,
                images=images[:self.settings.max_images_per_product],
                warnings=warnings,
            )
