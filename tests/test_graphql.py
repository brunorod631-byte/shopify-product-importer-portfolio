from app.shopify.graphql import CREATE_PRODUCT, FORCE_DRAFT, UPDATE_VARIANTS
from app.shopify.publishing import ProductPublisher


def test_user_error_selection_uses_supported_fields_only():
    assert "userErrors { field message code" not in CREATE_PRODUCT
    assert "userErrors{field message code" not in UPDATE_VARIANTS
    assert "userErrors { field message }" in CREATE_PRODUCT
    assert "userErrors{field message}" in UPDATE_VARIANTS
    assert "taxable" in UPDATE_VARIANTS


def test_final_product_state_is_forced_to_draft():
    assert "productUpdate" in FORCE_DRAFT
    assert "status publishedAt" in FORCE_DRAFT


def test_publisher_class_is_available():
    assert ProductPublisher is not None
