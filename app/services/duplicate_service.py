import hashlib
from sqlalchemy import or_,select
from app.models import ImportStatus,ProductImport
from app.utils.text import normalized
def product_hash(p):
    return hashlib.sha256("|".join([normalized(p.title),normalized(p.brand or ""),p.sku or "",p.barcode or "",p.mpn or ""]).encode()).hexdigest()
def find_completed_duplicate(session,p,exclude_id=None):
    query=select(ProductImport).where(
        ProductImport.status==ImportStatus.COMPLETED,
        ProductImport.shopify_product_id.is_not(None),
        or_(
            ProductImport.source_url==str(p.source_url),
            ProductImport.product_hash==product_hash(p),
        ),
    )
    if exclude_id is not None:
        query=query.where(ProductImport.id!=exclude_id)
    return session.scalar(query.order_by(ProductImport.id.desc()).limit(1))
