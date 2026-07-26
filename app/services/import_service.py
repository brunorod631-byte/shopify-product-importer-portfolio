from urllib.parse import urlsplit
from app.extractors.registry import get_extractor
from app.models import ImportStatus,ProductImport
from app.services.enhanced_description_service import EnhancedDescriptionProvider
from app.services.duplicate_service import product_hash
from app.services.price_service import CurrencyConverter, final_price
from app.utils.text import remove_product_codes, visible_specifications
from app.utils.urls import validate_public_url
class ImportService:
    def __init__(self,settings,session_factory):
        self.settings=settings; self.sessions=session_factory
        self.currency_converter=CurrencyConverter(settings)
    async def extract(self,url,user_id,markup=None):
        safe=validate_public_url(url)
        with self.sessions() as db:
            row=ProductImport(source_url=safe,domain=urlsplit(safe).hostname or "",telegram_user_id=user_id,status=ImportStatus.EXTRACTING)
            db.add(row);db.commit()
            try:
                p=await get_extractor(safe,self.settings).extract(safe)
                codes=[p.sku,p.mpn,p.barcode]
                for code in list(codes):
                    if code and "_" in code:
                        codes.extend(part for part in code.split("_") if len(part) >= 4)
                p.title=remove_product_codes(p.title,codes)
                if not p.title:
                    p.title=p.brand or p.category or "Producto"
                p.description=remove_product_codes(p.description,codes)
                p.specifications=visible_specifications(p.specifications)
                p.specifications={
                    remove_product_codes(key,codes): remove_product_codes(value,codes)
                    for key,value in p.specifications.items()
                    if remove_product_codes(key,codes) and remove_product_codes(value,codes)
                }
                p.included=[
                    cleaned
                    for item in p.included
                    if (cleaned:=remove_product_codes(item,codes))
                ]
                conversion=None
                if p.price is not None:
                    converter=(self.currency_converter.convert_to_uyu_brou if p.source=="ingco" else self.currency_converter.convert_to_uyu)
                    conversion=await converter(p.price,p.currency)
                if p.compare_at_price is not None:
                    converter=(self.currency_converter.convert_to_uyu_brou if p.source=="ingco" else self.currency_converter.convert_to_uyu)
                    compare_conversion=await converter(p.compare_at_price,p.currency)
                    p.compare_at_price=final_price(
                        compare_conversion.amount_uyu,
                        self.settings.default_markup_percent if markup is None else markup,
                        "UYU",
                    )
                price=final_price(conversion.amount_uyu if conversion else None,self.settings.default_markup_percent if markup is None else markup,"UYU")
                html,seo=EnhancedDescriptionProvider().generate(p); p.description=html
                row.status=ImportStatus.PREVIEW;row.extracted_json=p.model_dump_json();row.original_price=float(p.price) if p.price else None;row.final_price=float(price) if price else None;row.product_hash=product_hash(p);db.commit()
                return row,p,price,seo,conversion
            except Exception as exc:
                row.status=ImportStatus.FAILED;row.error=str(exc)[:1000];db.commit();raise
