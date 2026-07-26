import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ImportStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    EXTRACTING = "EXTRACTING"
    PREVIEW = "PREVIEW"
    CONFIRMED = "CONFIRMED"
    CREATING = "CREATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProductImport(Base):
    __tablename__ = "product_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, index=True)
    domain: Mapped[str] = mapped_column(String(255))
    telegram_user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    status: Mapped[ImportStatus] = mapped_column(Enum(ImportStatus))
    extracted_json: Mapped[str | None] = mapped_column(Text)
    original_price: Mapped[float | None] = mapped_column(Float)
    final_price: Mapped[float | None] = mapped_column(Float)
    shopify_product_id: Mapped[str | None] = mapped_column(String(255))
    admin_url: Mapped[str | None] = mapped_column(Text)
    product_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

