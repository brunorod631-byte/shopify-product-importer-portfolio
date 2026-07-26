from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ProductVariant(BaseModel):
    title: str = "Default Title"
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    sku: str | None = None
    barcode: str | None = None
    available: bool | None = None
    options: dict[str, str] = Field(default_factory=dict)


class ProductData(BaseModel):
    source_url: HttpUrl
    source: str = "generic"
    title: str
    brand: str | None = None
    category: str | None = None
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    currency: str | None = None
    description: str = ""
    specifications: dict[str, str] = Field(default_factory=dict)
    included: list[str] = Field(default_factory=list)
    variants: list[ProductVariant] = Field(default_factory=list)
    sku: str | None = None
    barcode: str | None = None
    mpn: str | None = None
    availability: str | None = None
    images: list[HttpUrl] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

