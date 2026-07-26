from decimal import Decimal
from pathlib import Path
import pytest
from PIL import Image
import io
from app.extractors.generic import best_html_title,parse_jsonld
from app.extractors.mercadolibre import MercadoLibreExtractor
from app.extractors.vicas import VicasExtractor,parse_vicas_html
from app.extractors.ferreteradelnorte import is_product_grid,parse_grid,parse_product
from bs4 import BeautifulSoup
from app.extractors.catalogs import IngcoExtractor
from app.extractors.orofino import OrofinoExtractor
from app.extractors.goldfarb import GoldfarbExtractor,product_from_payload
from app.extractors.rendered_images import choose_srcset
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.database import init_db
from app.models import ImportStatus,ProductImport
from app.services.duplicate_service import find_completed_duplicate,product_hash
from app.services.enhanced_description_service import EnhancedDescriptionProvider
from app.services.image_service import deduplicate,process_image
from app.services.price_service import parse_brou_rate
from app.services.price_service import CurrencyConverter, ExchangeRateError
from app.schemas import ProductData
from app.telegram.security import is_authorized
from app.telegram.keyboards import (create_publish_confirmation_keyboard,
    photo_confirmation_keyboard,preview_keyboard,
    publish_confirmation_keyboard)
from app.utils.money import apply_markup,parse_money
from app.utils.text import clean_title, remove_product_codes, visible_specifications
from app.utils.urls import UnsafeUrlError,normalize_url,validate_public_url

def test_normalize_url(): assert normalize_url("HTTPS://Example.COM/p?utm_source=x&a=1#z")=="https://example.com/p?a=1"

def test_orofino_uses_specific_extractor():
    assert OrofinoExtractor.supports("https://www.orofino.com.uy/shop/producto/")
    assert not OrofinoExtractor.supports("https://example.com/producto")

def test_goldfarb_payload_extracts_original_image():
    payload={"products":[{"itemCode":"4866","title":"Pala Tramontina","brand":{"name":"Tramontina"},"finalPrice":475,"category":"Palas","description":"Pala <br> fuerte","codeBars":"789","unitsPerItem":"PIEZA","images":[{"url":"https://goldfarb.blob.core.windows.net/goldfarb/imagenes/4866.jpg"}]}]}
    product=product_from_payload(payload,"https://www.goldfarb.com.uy/shop/products/4866",8)
    assert product.source=="goldfarb" and product.brand=="Tramontina"
    assert str(product.images[0]).endswith("/4866.jpg")
    assert product.price==Decimal("475") and product.currency=="UYU"

def test_goldfarb_uses_specific_extractor():
    assert GoldfarbExtractor.supports("https://www.goldfarb.com.uy/shop/products/4866")
    assert not GoldfarbExtractor.supports("https://example.com/shop/products/4866")

def test_srcset_selects_highest_resolution_image():
    value="/small.jpg 320w, /medium.jpg 800w, https://cdn.example.com/large.jpg 1600w"
    assert choose_srcset(value)=="https://cdn.example.com/large.jpg"

def test_generic_rejects_institutional_title_for_product_h1():
    html="<title>Empresa - Importador Mayorista de ferretería</title><main><h1>Taladro percutor 13 mm</h1></main>"
    soup=BeautifulSoup(html,"lxml")
    assert best_html_title(soup,{})=="Taladro percutor 13 mm"

def test_vicas_extracts_real_product_title_and_primary_image():
    html='''<title>VICAS - Importador Mayorista</title><div class="carousel-inner"><div class="item active"><img src="/files/bandeja.png"></div></div><div><h1 class="page-header">Bandeja plástica pintor GRANDE 29x37cm-SECUR</h1><p>Para rodillo</p></div>'''
    product=parse_vicas_html(html,"https://www.vicas.com.uy/productos/detalle/2138")
    assert product.title=="Bandeja plástica pintor GRANDE 29x37cm-SECUR"
    assert product.brand=="Secur" and str(product.images[0])=="https://www.vicas.com.uy/files/bandeja.png"
    assert VicasExtractor.supports("https://www.vicas.com.uy/productos/detalle/2138")

def test_ferretera_grid_and_product_title():
    grid='''<div class="tovar_item"><div class="tovar_img_wrapper" onclick="preview(3632132);"><img src="https://img.example/3632132/M.1.jpg"></div><span class="tovar_title">DISCO DIAMANTADO 230MM EMTOP</span><span class="tovar_price">4869</span></div>'''
    url="https://www.ferreteradelnorte.com/store/home.php?p=productsGrid&cat=32007"
    products=parse_grid(grid,url)
    assert is_product_grid(url) and products[0].title=="DISCO DIAMANTADO 230MM EMTOP"
    assert "producto=3632132" in products[0].url
    detail='''<div class="tovar_view_fotos"><div id="slider2"><img src="https://img.example/3632132/G.1.jpg"></div></div><div class="tovar_view_description"><div class="tovar_view_title">DISCO DIAMANTADO 230MM EMTOP</div><div class="tovar_article">4869</div><div class="tovar_brend">EMTOP</div><p>Stock: En Stock</p></div>'''
    product=parse_product(detail,products[0].url)
    assert product.title=="DISCO DIAMANTADO 230MM EMTOP" and product.brand=="EMTOP"
    assert str(product.images[0]).endswith("/G.1.jpg")

def test_brou_uses_dollar_sale_rate():
    html='''<table><tbody><tr><td><p class="moneda">Dólar</p></td><td><p class="valor">38,95000</p></td><td><p class="valor">41,35000</p></td><td><p class="valor">1,00000</p></td></tr></tbody></table>'''
    assert parse_brou_rate(html,"USD")==Decimal("41.35000")
@pytest.mark.parametrize("url",["file:///etc/passwd","http://127.0.0.1/x","http://10.0.0.1","http://[::1]/"])
def test_ssrf(url):
    with pytest.raises(UnsafeUrlError): validate_public_url(url)
def test_ssrf_dns_rebinding():
    fake=lambda *a,**k:[(None,None,None,None,("192.168.1.2",443))]
    with pytest.raises(UnsafeUrlError): validate_public_url("https://example.invalid",fake)
def test_mercadolibre_catalog_slug_can_supply_manual_preview_title():
    from urllib.parse import unquote,urlsplit
    url="https://www.mercadolibre.com.uy/camara-seguridad-solar-6mp/up/MLUU1"
    slug=[x for x in urlsplit(url).path.split("/") if x][0]
    assert unquote(slug).replace("-"," ").title()=="Camara Seguridad Solar 6Mp"
def test_mercadolibre_rejects_unrelated_minimal_jsonld_product():
    product=ProductData(source_url="https://www.mercadolibre.com.uy/producto",source="mercadolibre",title="Gz")
    assert not MercadoLibreExtractor._usable_structured(product)
def test_mercadolibre_accepts_complete_jsonld_product():
    product=ProductData(source_url="https://www.mercadolibre.com.uy/producto",source="mercadolibre",title="Camara de seguridad solar",price=Decimal("100"),currency="UYU")
    assert MercadoLibreExtractor._usable_structured(product)
def test_title(): assert clean_title("  Taladro   | Oferta ")=="Taladro"
def test_product_codes_are_hidden_from_visible_content():
    assert remove_product_codes("Taladro CDLI20880 20V", ["CDLI20880"]) == "Taladro 20V"
    assert remove_product_codes("Llave modelo DWE560 profesional") == "Llave modelo profesional"
    assert remove_product_codes("Amoladora P20S 20V 5AH") == "Amoladora 20V 5AH"
    assert remove_product_codes("2 baterías de 5.0Ah (FBLI20031)") == "2 baterías de 5.0Ah"
    assert remove_product_codes("Voltios de carga:220-240V~50/60Hz") == "Voltios de carga:220-240V~50/60Hz"
    assert visible_specifications({"Código":"CDLI20880","Potencia":"750 W"}) == {"Potencia":"750 W"}
def test_money(): assert parse_money("$ 1.234,50")==Decimal("1234.50")
def test_markup(): assert apply_markup(Decimal("100"),25)==Decimal("125")
@pytest.mark.asyncio
async def test_currency_conversion_to_uyu_uses_cached_current_rate():
    converter=CurrencyConverter(Settings(_env_file=None))
    converter._cache["USD"]=(datetime.now(timezone.utc)+timedelta(hours=1),Decimal("40.25"),"test-date")
    result=await converter.convert_to_uyu(Decimal("10"),"USD")
    assert result.amount_uyu==Decimal("402.50") and result.rate==Decimal("40.25")
@pytest.mark.asyncio
async def test_currency_conversion_never_assumes_missing_currency():
    converter=CurrencyConverter(Settings(_env_file=None))
    with pytest.raises(ExchangeRateError,match="sin indicar moneda"):
        await converter.convert_to_uyu(Decimal("100"),None)
def test_description_no_invention():
    p=ProductData(source_url="https://example.com",title="Martillo",specifications={"Peso":"500 g"})
    html,seo=EnhancedDescriptionProvider().generate(p);assert "500 g" in html and "voltaje" not in html.lower() and len(seo)<=160
def test_description_translates_only_supported_evidence_into_benefits():
    p=ProductData(
        source_url="https://example.com",title="Amoladora a batería",brand="INGCO",
        specifications={"Motor":"Sin carbones"},included=["Maletín de transporte"],
    )
    html,_=EnhancedDescriptionProvider().generate(p)
    assert "libertad de movimiento" in html and "reducir el mantenimiento" in html
    assert "garantía" not in html.lower() and "potencia" not in html.lower()


def test_description_is_complete_and_uses_product_evidence():
    p = ProductData(
        source_url="https://example.com",
        title="Bomba de agua sumergible",
        brand="WADFOW",
        category="Bombas de agua",
        specifications={"Caudal máximo": "50 l/min", "Voltaje": "12 V"},
        included=["Cable de alimentación"],
    )
    html, seo = EnhancedDescriptionProvider().generate(p)
    assert all(
        heading in html
        for heading in (
            "Ventajas destacadas",
            "Características principales",
            "Usos recomendados",
            "Contenido incluido",
            "Información importante",
        )
    )
    assert "50 l/min" in html and "12 V" in html and "Movimiento de agua" in html
    assert "garantía" not in html.lower() and len(seo) <= 160
def test_jsonld():
    html=Path("tests/fixtures/product.html").read_text(encoding="utf-8");p=parse_jsonld(html,"https://example.com/p")
    assert p and p.title=="Taladro Profesional" and p.price==Decimal("3990.00") and p.specifications["Potencia"]=="750 W"
@pytest.mark.asyncio
async def test_ingco_microdata_price_and_specs(monkeypatch):
    fixture=Path("tests/fixtures/ingco_product.html").read_text(encoding="utf-8")
    async def fake_fetch(self,url):
        return fixture,url
    monkeypatch.setattr(IngcoExtractor,"fetch",fake_fetch)
    extractor=IngcoExtractor(Settings(_env_file=None))
    product=await extractor.extract("https://www.ingcotools.com.uy/producto")
    assert product.price==Decimal("214.22") and product.currency=="USD"
    assert product.brand=="INGCO" and product.sku=="ING_CAGLI2211532"
    assert product.specifications["Voltaje"]=="20V" and "Valija" in product.included

@pytest.mark.asyncio
async def test_ingco_visible_catalog_markup_and_legacy_domain(monkeypatch):
    fixture = """<html><head><meta property='og:title' content='TALADRO INGCO CDLI1234'></head>
    <body><h1>TALADRO INGCO CDLI1234</h1><div>Antes USD 99,00</div>
    <div>Ahora USD 79,90 IVA inc.</div><div>Cód.ING_CDLI1234</div></body></html>"""
    async def fake_fetch(self, url):
        return fixture, url
    monkeypatch.setattr(IngcoExtractor, "fetch", fake_fetch)
    assert IngcoExtractor.supports("https://web2023.ingcotools.com.uy/productos/productos.php?id=1")
    product = await IngcoExtractor(Settings(_env_file=None)).extract(
        "https://web2023.ingcotools.com.uy/productos/productos.php?id=1"
    )
    assert product.price == Decimal("79.90") and product.currency == "USD"
    assert product.sku == "ING_CDLI1234" and product.brand == "INGCO"
def test_images_invalid_and_duplicate():
    assert process_image(b"not image") is None
    out=io.BytesIO();Image.new("RGB",(300,300),"red").save(out,"PNG");img=process_image(out.getvalue());assert img and len(deduplicate([img,img]))==1
def test_authorization(): assert is_authorized(123,{123}) and not is_authorized(999,{123})
def test_only_completed_shopify_product_is_duplicate():
    settings=Settings(
        _env_file=None,
        database_url="sqlite:///:memory:",
    )
    sessions=init_db(settings)
    product=ProductData(
        source_url="https://example.com/producto",
        title="Taladro profesional",
        sku="ABC123",
    )
    with sessions() as db:
        preview=ProductImport(
            source_url=str(product.source_url),domain="example.com",
            telegram_user_id=1,status=ImportStatus.PREVIEW,
            product_hash=product_hash(product),
        )
        completed=ProductImport(
            source_url=str(product.source_url),domain="example.com",
            telegram_user_id=1,status=ImportStatus.COMPLETED,
            product_hash=product_hash(product),
            shopify_product_id="gid://shopify/Product/123",
        )
        db.add_all([preview,completed]);db.commit()
        assert find_completed_duplicate(db,product,exclude_id=preview.id).id==completed.id
        assert find_completed_duplicate(db,product,exclude_id=completed.id) is None
def test_preview_button_contains_persistent_import_id():
    keyboard=preview_keyboard(42)
    assert keyboard.inline_keyboard[0][0].callback_data=="assign_photo:42"
    assert keyboard.inline_keyboard[1][0].callback_data=="create:42"
    confirm=publish_confirmation_keyboard(42)
    assert confirm.inline_keyboard[0][0].callback_data=="publish_confirm:42"
    create_publish=create_publish_confirmation_keyboard(42)
    assert create_publish.inline_keyboard[0][0].callback_data=="create_publish_confirm:42"

def test_assign_photo_keyboards_keep_import_id():
    confirm=photo_confirmation_keyboard(42)
    assert [row[0].callback_data for row in confirm.inline_keyboard]==[
        "photo_confirm:42","assign_photo:42","photo_cancel:42"
    ]
    assert all(len(button.callback_data.encode())<=64 for row in confirm.inline_keyboard for button in row)
