from app.shopify.client import ShopifyUserError
from app.shopify.graphql import PUBLICATIONS, PUBLISH_PRODUCT, SET_PRODUCT_STATUS


class ProductPublisher:
    def __init__(self, client):
        self.client = client

    async def _set_status(self, product_id: str, status: str) -> None:
        data = await self.client.execute(
            SET_PRODUCT_STATUS, {"product": {"id": product_id, "status": status}}
        )
        errors = data["productUpdate"]["userErrors"]
        if errors:
            raise ShopifyUserError(errors)

    async def _online_publication(self) -> dict:
        data = await self.client.execute(PUBLICATIONS)
        publications = data["publications"]["nodes"]
        candidates = [
            item for item in publications
            if item["name"].strip().lower() in {"online store", "tienda online"}
        ]
        if not candidates:
            future_capable = [item for item in publications if item["supportsFuturePublishing"]]
            candidates = future_capable if len(future_capable) == 1 else []
        if len(candidates) != 1:
            raise ShopifyUserError([{
                "field": ["publication"],
                "message": "No se pudo identificar un único canal Tienda online",
            }])
        return candidates[0]

    async def prepare_online(self, product_id: str) -> dict:
        """Asocia el canal sin activar el borrador ni hacerlo visible."""
        publication = await self._online_publication()
        result = await self.client.execute(
            PUBLISH_PRODUCT,
            {"id": product_id, "input": [{"publicationId": publication["id"]}]},
        )
        errors = result["publishablePublish"]["userErrors"]
        if errors:
            raise ShopifyUserError(errors)
        return {"publication": publication, "result": result["publishablePublish"]}

    async def publish_online(self, product_id: str) -> dict:
        await self._set_status(product_id, "ACTIVE")
        try:
            return await self.prepare_online(product_id)
        except Exception:
            await self._set_status(product_id, "DRAFT")
            raise
