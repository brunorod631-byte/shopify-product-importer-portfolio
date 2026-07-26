import html
from decimal import Decimal,InvalidOperation
import httpx
from telegram import InlineKeyboardButton,InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler,CommandHandler,MessageHandler,filters
from app.models import ImportStatus
from app.schemas import ProductData
from app.services.enhanced_description_service import EnhancedDescriptionProvider
from app.services.price_service import final_price
from app.services.image_service import process_image
from app.shopify.client import ShopifyClient
from app.shopify.products import ProductCreator
from app.shopify.publishing import ProductPublisher
from app.telegram.keyboards import (create_publish_confirmation_keyboard,
    photo_confirmation_keyboard,preview_keyboard,
    publish_confirmation_keyboard,publish_keyboard)
from app.telegram.security import authorized

def _draft(context): return context.user_data.get("draft")
def _preview(p,price,markup,conversion=None):
    exchange = ""
    if conversion and conversion.original_currency != "UYU":
        exchange = (f"\nConversión: 1 {conversion.original_currency} = {conversion.rate} UYU"
                    f"\nCotización: {html.escape(conversion.rate_date[:40])}")
    return (f"<b>{html.escape(p.title)}</b>\nMarca: {html.escape(p.brand or 'No indicada')}\nPrecio origen: {p.price or 'No indicado'} {p.currency or ''}{exchange}\n"
            f"Recargo: {markup}%\nPrecio final: {price or 'No indicado'} UYU\nImágenes: {len(p.images)}\nFuente: {p.source}\nResumen: {html.escape(p.description[:350])}")
@authorized
async def start(update,context): await update.message.reply_text("Enviame una URL pública de producto. Todo se crea como BORRADOR. Tu ID autorizado es: "+str(update.effective_user.id))
@authorized
async def help_cmd(update,context): await update.message.reply_text("Enviá un enlace HTTP/HTTPS. Revisá la vista previa, editá si hace falta y pulsá Crear borrador.")
@authorized
async def config_cmd(update,context):
    s=context.application.bot_data["settings"]; await update.message.reply_text(f"API Shopify: {s.shopify_api_version}\nEstado: DRAFT\nMoneda: {s.default_currency}\nRecargo: {context.user_data.get('markup',s.default_markup_percent)}%\nMáx. imágenes: {s.max_images_per_product}")
@authorized
async def status_cmd(update,context):
    try: shop=await ProductCreator(ShopifyClient(context.application.bot_data["settings"])).health(); msg=f"Telegram: OK\nBase de datos: OK\nShopify: OK ({shop['name']})"
    except Exception as exc: msg=f"Telegram: OK\nBase de datos: OK\nShopify: no disponible ({str(exc)[:250]})"
    await update.message.reply_text(msg)
@authorized
async def markup_cmd(update,context):
    try: value=float(context.args[0]); assert 0<=value<=1000
    except (IndexError,ValueError,AssertionError): await update.message.reply_text("Uso: /recargo 25 (entre 0 y 1000)");return
    context.user_data["markup"]=value;await update.message.reply_text(f"Recargo futuro: {value}%")
@authorized
async def cancel_cmd(update,context): context.user_data.pop("draft",None);await update.message.reply_text("Importación cancelada.")
@authorized
async def publish_cmd(update,context):
    from sqlalchemy import select
    from app.models import ProductImport
    sf=context.application.bot_data["sessions"]
    with sf() as db:
        row=db.scalar(
            select(ProductImport)
            .where(
                ProductImport.telegram_user_id==update.effective_user.id,
                ProductImport.shopify_product_id.is_not(None),
            )
            .order_by(ProductImport.id.desc())
            .limit(1)
        )
    if not row:
        await update.message.reply_text("No hay ningún producto creado para publicar.")
        return
    await update.message.reply_text(
        f"Último producto creado: #{row.id}\nRevíselo antes de publicar:\n{row.admin_url}",
        reply_markup=publish_keyboard(row.id),
    )
@authorized
async def history_cmd(update,context):
    sf=context.application.bot_data["sessions"]
    from app.database import recent
    with sf() as db: rows=recent(db,update.effective_user.id)
    await update.message.reply_text("\n".join(f"#{x.id} {x.status.value} {x.source_url[:70]}" for x in rows) or "Sin historial.")
@authorized
async def url_handler(update,context):
    from app.extractors.ferreteradelnorte import FerreteraDelNorteExtractor,is_product_grid
    url=update.message.text.strip()
    if is_product_grid(url) and FerreteraDelNorteExtractor.supports(url):
        try: products=await FerreteraDelNorteExtractor(context.application.bot_data["settings"]).discover(url)
        except Exception as exc: await update.message.reply_text("No pude leer la grilla: "+str(exc)[:300]);return
        if not products: await update.message.reply_text("No encontré productos en esta página.");return
        context.user_data["fdn_grid"]={item.product_id:item.url for item in products}
        rows=[[InlineKeyboardButton(item.title[:58],callback_data=f"fdn_select:{item.product_id}")] for item in products[:20]]
        rows.append([InlineKeyboardButton("❌ Cancelar",callback_data="fdn_cancel")])
        await update.message.reply_text(f"Encontré {len(products)} productos en esta página. Elegí cuál querés importar:",reply_markup=InlineKeyboardMarkup(rows));return
    await _process_product_url(update.message,context,url,update.effective_user.id)

async def _process_product_url(message,context,url,user_id):
    service=context.application.bot_data["import_service"];markup=context.user_data.get("markup",service.settings.default_markup_percent)
    try: row,p,price,seo,conversion=await service.extract(url,user_id,markup)
    except Exception as exc: await message.reply_text("No se pudo extraer: "+str(exc)[:500]);return
    context.user_data["draft"]={"row_id":row.id,"product":p,"price":price,"seo":seo,"markup":markup,"conversion":conversion}
    kwargs={"caption":_preview(p,price,markup,conversion),"parse_mode":ParseMode.HTML,"reply_markup":preview_keyboard(row.id)}
    if p.images:
        try: await message.reply_photo(str(p.images[0]),**kwargs);return
        except Exception:
            try:
                settings=context.application.bot_data["settings"]
                async with httpx.AsyncClient(timeout=settings.request_timeout_seconds,follow_redirects=True) as client:
                    response=await client.get(str(p.images[0]),headers={"User-Agent":"ShopifyTelegramImporter/1.0","Referer":str(p.source_url),"Accept":"image/*"})
                    response.raise_for_status();processed=process_image(response.content)
                if processed: await message.reply_photo(processed.content,**kwargs);return
            except Exception: pass
    await message.reply_text(kwargs.pop("caption"),**kwargs)
@authorized
async def callback(update,context):
    q=update.callback_query;await q.answer();draft=_draft(context)
    action,_,raw_id=q.data.partition(":")
    if action=="fdn_cancel":
        context.user_data.pop("fdn_grid",None);await q.message.reply_text("Selección cancelada.");return
    if action=="fdn_select" and raw_id.isdigit():
        url=context.user_data.get("fdn_grid",{}).get(raw_id)
        if not url: await q.message.reply_text("La selección venció. Reenviá el enlace de la grilla.");return
        context.user_data.pop("fdn_grid",None)
        await _process_product_url(q.message,context,url,update.effective_user.id);return
    publish_after_create=False
    if action=="create_publish_request" and raw_id.isdigit():
        await q.message.reply_text(
            "Se creará el producto y quedará visible inmediatamente en Tienda online. ¿Confirma?",
            reply_markup=create_publish_confirmation_keyboard(int(raw_id)),
        )
        return
    if action=="create_publish_confirm":
        publish_after_create=True
        action="create"
    if action=="publish_request" and raw_id.isdigit():
        await q.message.reply_text(
            "Esto hará visible el producto inmediatamente en la tienda online. ¿Confirma?",
            reply_markup=publish_confirmation_keyboard(int(raw_id)),
        )
        return
    if action=="publish_cancel":
        await q.message.reply_text("Publicación cancelada.")
        return
    if action=="publish_confirm" and raw_id.isdigit():
        sf=context.application.bot_data["sessions"]
        from app.models import ProductImport
        with sf() as db:
            row=db.get(ProductImport,int(raw_id))
            valid=row and row.telegram_user_id==update.effective_user.id and row.shopify_product_id
            product_id=row.shopify_product_id if valid else None
            admin_url=row.admin_url if valid else None
        if not product_id:
            await q.message.reply_text("No se encontró un producto válido para publicar.")
            return
        try:
            await ProductPublisher(ShopifyClient(context.application.bot_data["settings"])).publish_online(product_id)
            await q.message.reply_text(f"Producto publicado en Tienda online.\n{admin_url}")
        except Exception as exc:
            await q.message.reply_text("No se pudo publicar; se restauró como borrador: "+str(exc)[:500])
        return
    if not draft and action=="create" and raw_id.isdigit():
        sf=context.application.bot_data["sessions"]
        from app.models import ProductImport
        with sf() as db:
            row=db.get(ProductImport,int(raw_id))
            if row and row.telegram_user_id==update.effective_user.id and row.extracted_json:
                product=ProductData.model_validate_json(row.extracted_json)
                _,seo=EnhancedDescriptionProvider().generate(product)
                draft={"row_id":row.id,"product":product,"price":row.final_price,
                       "seo":seo,"markup":0.0,"conversion":None}
                context.user_data["draft"]=draft
    if not draft:
        await q.message.reply_text("Esta vista previa venció. Reenvíe la URL para generar una nueva.")
        return
    if action=="assign_photo":
        context.user_data.pop("pending_photo",None)
        context.user_data["editing"]="photo_upload"
        await q.message.reply_text("Tocá el clip 📎 y elegí la imagen desde Galería o Archivos. Se aceptan JPG, PNG y WEBP. La foto actual solo se reemplazará después de confirmar.")
        return
    if action=="photo_cancel":
        context.user_data.pop("editing",None);context.user_data.pop("pending_photo",None)
        await q.message.reply_text("Asignación de foto cancelada.",reply_markup=preview_keyboard(draft["row_id"]))
        return
    if action=="photo_confirm":
        pending=context.user_data.pop("pending_photo",None)
        if not pending:
            await q.message.reply_text("La vista previa de la foto venció. Volvé a asignarla.")
            return
        draft["manual_photo"]=pending
        await q.message.reply_text("Foto asignada. Se usará como imagen principal del producto.",reply_markup=preview_keyboard(draft["row_id"]))
        return
    if action=="cancel":
        context.user_data.pop("draft",None)
        await q.message.reply_text("Cancelado.")
        return
    if q.data.startswith("edit_"): context.user_data["editing"]=q.data[5:];await q.message.reply_text("Enviá el nuevo valor en un mensaje.");return
    if action=="create":
        if draft.get("price") is None:
            await q.message.reply_text(
                "No puedo crear el borrador sin un precio final en UYU. "
                "Use Editar precio y escriba el importe en pesos uruguayos."
            )
            return
        sf=context.application.bot_data["sessions"]
        with sf() as db:
            from app.services.duplicate_service import find_completed_duplicate
            duplicate=find_completed_duplicate(
                db,draft["product"],exclude_id=draft["row_id"]
            )
            if duplicate:
                await q.message.reply_text(
                    "Este producto ya fue creado en Shopify; no se generó otro borrador.\n"
                    f"{duplicate.admin_url or duplicate.shopify_product_id}"
                )
                return
        await q.message.reply_text("Creando borrador en Shopify…")
        try:
            client=ShopifyClient(context.application.bot_data["settings"])
            manual_photo=draft.get("manual_photo")
            if manual_photo and manual_photo["kind"]=="telegram":
                staged_url=await client.stage_image(manual_photo["content"])
                draft["product"].images=[staged_url]
                _persist_draft(context,draft)
            with sf() as db:
                from app.models import ProductImport
                row=db.get(ProductImport,draft["row_id"])
                row.status=ImportStatus.CREATING
                db.commit()
            created,url=await ProductCreator(client).create_draft(draft["product"],draft["price"],draft["seo"])
            with sf() as db:
                from app.models import ProductImport
                row=db.get(ProductImport,draft["row_id"]);row.status=ImportStatus.COMPLETED;row.shopify_product_id=created["id"];row.admin_url=url;db.commit()
            await q.message.reply_text(f"Borrador creado.\nID: {created['id']}\nEstado: DRAFT\n{url}",reply_markup=publish_keyboard(row.id))
            if publish_after_create:
                await ProductPublisher(ShopifyClient(context.application.bot_data["settings"])).publish_online(created["id"])
                await q.message.reply_text(f"Producto publicado en Tienda online.\n{url}")
            context.user_data.pop("draft",None)
        except Exception as exc:
            with sf() as db:
                from app.models import ProductImport
                row=db.get(ProductImport,draft["row_id"])
                row.status=ImportStatus.FAILED;row.error=str(exc)[:1000];row.retry_count+=1;db.commit()
            await q.message.reply_text("Shopify rechazó la operación: "+str(exc)[:500])
@authorized
async def edit_value(update,context):
    field=context.user_data.get("editing");draft=_draft(context)
    if not field or not draft:return
    value=update.message.text.strip();p=draft["product"]
    try:
        if field=="title": p.title=value[:255]
        elif field=="description": p.description=value
        elif field=="price": draft["price"]=Decimal(value.replace(",","."))
        elif field=="markup":
            draft["markup"]=float(value)
            base=draft["conversion"].amount_uyu if draft.get("conversion") else p.price
            draft["price"]=final_price(base,draft["markup"],"UYU")
    except (ValueError,InvalidOperation,httpx.HTTPError): await update.message.reply_text("No pude validar ese valor o imagen. Intentá nuevamente o cancelá.");return
    context.user_data.pop("editing",None)
    await update.message.reply_text(_preview(p,draft["price"],draft["markup"],draft.get("conversion")),parse_mode=ParseMode.HTML,reply_markup=preview_keyboard(draft["row_id"]))

def _persist_draft(context,draft):
    sf=context.application.bot_data["sessions"]
    from app.models import ProductImport
    with sf() as db:
        row=db.get(ProductImport,draft["row_id"])
        if row:
            row.extracted_json=draft["product"].model_dump_json();db.commit()

@authorized
async def photo_value(update,context):
    if context.user_data.get("editing")!="photo_upload": return
    draft=_draft(context)
    if not draft:
        context.user_data.pop("editing",None);await update.message.reply_text("La vista previa venció.");return
    settings=context.application.bot_data["settings"]
    attachment=update.message.photo[-1] if update.message.photo else update.message.document
    mime_type=getattr(attachment,"mime_type",None) or "image/jpeg"
    if mime_type not in {"image/jpeg","image/png","image/webp"}:
        await update.message.reply_text("Ese archivo no es una imagen JPG, PNG o WEBP. Elegí otra imagen con el clip 📎.");return
    if attachment.file_size and attachment.file_size>settings.max_download_bytes:
        await update.message.reply_text("La foto es demasiado grande.");return
    telegram_file=await attachment.get_file();content=bytes(await telegram_file.download_as_bytearray())
    processed=process_image(content)
    if not processed:
        await update.message.reply_text("No pude validar esa imagen. Enviá otra foto JPG, PNG o WEBP.");return
    context.user_data.pop("editing",None)
    context.user_data["pending_photo"]={"kind":"telegram","content":processed.content}
    await update.message.reply_photo(processed.content,caption="Vista previa de la foto",reply_markup=photo_confirmation_keyboard(draft["row_id"]))
def register(application):
    for cmd,fn in [("start",start),("ayuda",help_cmd),("estado",status_cmd),("config",config_cmd),("recargo",markup_cmd),("cancelar",cancel_cmd),("historial",history_cmd),("publicar",publish_cmd),("reintentar",help_cmd)]: application.add_handler(CommandHandler(cmd,fn))
    image_files=filters.Document.IMAGE
    application.add_handler(CallbackQueryHandler(callback));application.add_handler(MessageHandler(filters.PHOTO|image_files,photo_value),group=0);application.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,edit_value),group=0);application.add_handler(MessageHandler(filters.Regex(r"^https?://"),url_handler),group=1)
