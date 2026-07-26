import httpx
import pytest

from app.config import Settings
from app.shopify.client import ShopifyClient, ShopifyError, ShopifyUserError


def test_shopify_user_errors():
    error=ShopifyUserError([{"field":["product","title"],"message":"is required"}])
    assert "product.title" in str(error) and "is required" in str(error)


@pytest.mark.asyncio
async def test_dev_dashboard_credentials_are_exchanged_and_cached():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/admin/oauth/access_token"
        assert b"grant_type=client_credentials" in request.content
        assert b"client_id=client-id" in request.content
        return httpx.Response(200, json={"access_token": "temporary-token", "expires_in": 86399})

    settings = Settings(
        _env_file=None,
        shopify_store_domain="demo.myshopify.com",
        shopify_client_id="client-id",
        shopify_client_secret="client-secret",  # noqa: S106 - synthetic test value
    )
    shopify = ShopifyClient(settings)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await shopify._get_access_token(client) == "temporary-token"
        assert await shopify._get_access_token(client) == "temporary-token"
    assert calls == 1


@pytest.mark.asyncio
async def test_missing_shopify_credentials_has_clear_error():
    settings = Settings(_env_file=None, shopify_store_domain="demo.myshopify.com")
    shopify = ShopifyClient(settings)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)) as client:
        with pytest.raises(ShopifyError, match="SHOPIFY_CLIENT_ID"):
            await shopify._get_access_token(client)
