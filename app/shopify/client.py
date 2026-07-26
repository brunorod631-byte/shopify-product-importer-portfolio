import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


class ShopifyError(RuntimeError):
    pass


class ShopifyUserError(ShopifyError):
    def __init__(self, errors):
        self.errors = errors
        message = "; ".join(
            f"{'.'.join(map(str, error.get('field') or []))}: {error['message']}"
            for error in errors
        )
        super().__init__(message)


class ShopifyClient:
    def __init__(self, settings):
        self.settings = settings
        self.url = (
            f"https://{settings.shopify_store_domain}/admin/api/"
            f"{settings.shopify_api_version}/graphql.json"
        )
        self._access_token = ""
        self._token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._token_lock = asyncio.Lock()

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        if self.settings.shopify_admin_access_token:
            return self.settings.shopify_admin_access_token
        if not (self.settings.shopify_client_id and self.settings.shopify_client_secret):
            raise ShopifyError("Faltan SHOPIFY_CLIENT_ID y SHOPIFY_CLIENT_SECRET")
        now = datetime.now(timezone.utc)
        if self._access_token and now < self._token_expires_at:
            return self._access_token
        async with self._token_lock:
            now = datetime.now(timezone.utc)
            if self._access_token and now < self._token_expires_at:
                return self._access_token
            response = await client.post(
                f"https://{self.settings.shopify_store_domain}/admin/oauth/access_token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.shopify_client_id,
                    "client_secret": self.settings.shopify_client_secret,
                },
            )
            if response.status_code in {400, 401, 403}:
                try:
                    payload = response.json()
                    detail = payload.get("error_description") or payload.get("error")
                except ValueError:
                    text = response.text.lower()
                    known = ("app_not_installed", "application_cannot_be_found", "shop_not_permitted")
                    detail = next((code for code in known if code in text), None)
                detail = detail or f"credenciales rechazadas (HTTP {response.status_code})"
                raise ShopifyError(f"No se pudo autenticar la app en Shopify: {detail}")
            response.raise_for_status()
            payload = response.json()
            self._access_token = payload["access_token"]
            lifetime = max(60, int(payload.get("expires_in", 86399)) - 300)
            self._token_expires_at = now + timedelta(seconds=lifetime)
            return self._access_token

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    async def execute(self, query, variables=None):
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            token = await self._get_access_token(client)
            response = await client.post(
                self.url,
                headers={"X-Shopify-Access-Token": token},
                json={"query": query, "variables": variables or {}},
            )
            if response.status_code in {401, 403}:
                raise ShopifyError(
                    f"Shopify rechazó la credencial o permisos (HTTP {response.status_code})"
                )
            if response.status_code == 429:
                await asyncio.sleep(float(response.headers.get("Retry-After", "2")))
                raise httpx.TransportError("Rate limit")
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise ShopifyError("; ".join(item["message"] for item in payload["errors"]))
            return payload["data"]

    async def stage_image(self, content: bytes, filename: str = "producto.jpg", mime_type: str = "image/jpeg") -> str:
        from app.shopify.graphql import STAGED_UPLOADS_CREATE
        data = await self.execute(STAGED_UPLOADS_CREATE, {"input": [{
            "resource": "IMAGE", "filename": filename, "mimeType": mime_type,
            "httpMethod": "POST", "fileSize": str(len(content)),
        }]})
        result = data["stagedUploadsCreate"]
        if result["userErrors"]:
            raise ShopifyUserError(result["userErrors"])
        target = result["stagedTargets"][0]
        fields = {item["name"]: item["value"] for item in target["parameters"]}
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(target["url"], data=fields, files={"file": (filename, content, mime_type)})
            response.raise_for_status()
        return target["resourceUrl"]
