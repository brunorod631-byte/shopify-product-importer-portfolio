import logging
from urllib.parse import urlsplit

import httpx
from playwright.async_api import async_playwright

from app.extractors.base import ExtractionError
from app.extractors.generic import GenericExtractor, parse_jsonld

logger = logging.getLogger(__name__)


class OrofinoExtractor(GenericExtractor):
    @classmethod
    def supports(cls, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return host == "orofino.com.uy" or host.endswith(".orofino.com.uy")

    async def extract(self, url: str):
        try:
            product = await super().extract(url)
            product.source = "orofino"
            return product
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            logger.info("Orofino bloqueó HTTP normal; usando navegador renderizado url=%s", url)
        except ExtractionError:
            logger.info("Orofino no expuso datos por HTTP; usando navegador renderizado url=%s", url)
        return await self._extract_rendered(url)

    async def _extract_rendered(self, url: str):
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/126.0.0.0 Safari/537.36"),
                    locale="es-UY",
                )

                async def restrict(route):
                    host = (urlsplit(route.request.url).hostname or "").lower()
                    allowed = host == "orofino.com.uy" or host.endswith(".orofino.com.uy")
                    unnecessary = route.request.resource_type in {"font", "media"}
                    await (route.continue_() if allowed and not unnecessary else route.abort())

                await context.route("**/*", restrict)
                page = await context.new_page()
                response = await page.goto(
                    url, wait_until="domcontentloaded",
                    timeout=self.settings.request_timeout_seconds * 1000,
                )
                if not response or response.status >= 400:
                    raise ExtractionError("Orofino rechazó la carga pública")
                html = await page.content()
                product = parse_jsonld(html, page.url, "orofino")
                if not product:
                    raise ExtractionError("Orofino no expuso datos del producto")
                product.warnings.append(
                    "Orofino requirió carga con navegador; revise los datos antes de confirmar"
                )
                return product
            finally:
                await browser.close()
