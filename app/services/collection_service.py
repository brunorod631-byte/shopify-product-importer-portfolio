from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.models import ImportStatus, ProductImport
from app.shopify.client import ShopifyUserError
from app.shopify.products import ProductCreator
from app.utils.urls import validate_public_url


@dataclass
class BatchResult:
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    collection_id: str | None = None
    collection_url: str | None = None


class CollectionImportService:
    def __init__(self, settings, sessions, import_service, shopify_client):
        self.settings = settings
        self.sessions = sessions
        self.import_service = import_service
        self.client = shopify_client

    async def discover(self, url: str) -> tuple[str, list[str]]:
        safe = validate_public_url(url)
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            headers={"User-Agent": "ShopifyTelegramImporter/1.0 (+local merchant importer)"},
        ) as client:
            response = await client.get(safe, follow_redirects=True)
            response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")
        title_tag = soup.select_one("h1")
        title = title_tag.get_text(" ", strip=True).title() if title_tag else "Colección importada"
        links: list[str] = []
        for item in soup.select('[itemtype*="Product"]'):
            anchor = item.select_one("a[href]")
            if anchor:
                product_url = urljoin(str(response.url), anchor.get("href"))
                if product_url not in links:
                    links.append(product_url)
        return title, links[:250]

    async def import_all(self, url: str, user_id: int, title: str | None = None) -> BatchResult:
        discovered_title, urls = await self.discover(url)
        result = BatchResult()
        creator = ProductCreator(self.client)
        for product_url in urls:
            with self.sessions() as db:
                existing = db.scalar(
                    select(ProductImport).where(
                        ProductImport.source_url == product_url,
                        ProductImport.status == ImportStatus.COMPLETED,
                    ).limit(1)
                )
            if existing:
                result.skipped.append(product_url)
                if existing.shopify_product_id:
                    result.created.append(existing.shopify_product_id)
                continue
            try:
                row, product, price, seo, _ = await self.import_service.extract(
                    product_url, user_id, self.settings.default_markup_percent
                )
                created, admin_url = await creator.create_draft(product, price, seo)
                with self.sessions() as db:
                    stored = db.get(ProductImport, row.id)
                    stored.status = ImportStatus.COMPLETED
                    stored.shopify_product_id = created["id"]
                    stored.admin_url = admin_url
                    db.commit()
                result.created.append(created["id"])
            except Exception as exc:
                result.failed.append((product_url, str(exc)[:300]))
        unique_ids = list(dict.fromkeys(result.created))
        if unique_ids:
            mutation = """mutation CreateCollection($input:CollectionInput!){collectionCreate(input:$input){collection{id title handle} userErrors{field message}}}"""
            data = await self.client.execute(mutation, {"input": {
                "title": title or discovered_title,
                "descriptionHtml": "<p>Productos importados y revisables desde el catálogo de origen.</p>",
                "products": unique_ids,
            }})
            payload = data["collectionCreate"]
            if payload["userErrors"]:
                raise ShopifyUserError(payload["userErrors"])
            collection = payload["collection"]
            result.collection_id = collection["id"]
            store = self.settings.shopify_store_domain.split(".")[0]
            numeric = collection["id"].rsplit("/", 1)[-1]
            result.collection_url = f"https://admin.shopify.com/store/{store}/collections/{numeric}"
        return result
