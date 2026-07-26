from abc import ABC, abstractmethod
import httpx
from app.config import Settings
from app.schemas import ProductData
from app.utils.urls import validate_public_url

class ExtractionError(RuntimeError): pass

class BaseExtractor(ABC):
    def __init__(self, settings: Settings): self.settings = settings
    @classmethod
    @abstractmethod
    def supports(cls, url: str) -> bool: ...
    async def fetch(self, url: str) -> tuple[str, str]:
        current = validate_public_url(url)
        headers = {"User-Agent": "ShopifyTelegramImporter/1.0 (+local merchant importer)"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=False, timeout=self.settings.request_timeout_seconds) as client:
            for _ in range(self.settings.max_redirects + 1):
                response = await client.get(current)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location: raise ExtractionError("Redirección sin destino")
                    current = validate_public_url(str(response.url.join(location))); continue
                response.raise_for_status()
                if len(response.content) > self.settings.max_download_bytes: raise ExtractionError("Página demasiado grande")
                if "html" not in response.headers.get("content-type", ""): raise ExtractionError("El destino no es HTML")
                return response.text, str(response.url)
        raise ExtractionError("Demasiadas redirecciones")
    @abstractmethod
    async def extract(self, url: str) -> ProductData: ...
