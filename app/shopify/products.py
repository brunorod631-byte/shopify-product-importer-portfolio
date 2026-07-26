from app.shopify.client import ShopifyUserError
from app.shopify.graphql import CREATE_PRODUCT,FORCE_DRAFT,SHOP_QUERY,UPDATE_VARIANTS
from app.shopify.publishing import ProductPublisher
class ProductCreator:
    def __init__(self,client): self.client=client
    async def health(self):
        data=await self.client.execute(SHOP_QUERY); scopes={x["handle"] for x in data["currentAppInstallation"]["accessScopes"]}; missing={"write_products"}-scopes
        if missing: raise ShopifyUserError([{"field":["accessScopes"],"message":"Falta el permiso: "+", ".join(sorted(missing))}])
        return data["shop"]
    async def create_draft(self,p,price,seo):
        tags=["imported-by-telegram",f"source-{p.source}","source-url"]
        media=[{"originalSource":str(u),"mediaContentType":"IMAGE","alt":f"{p.title} - imagen {i+1}"} for i,u in enumerate(p.images[:self.client.settings.max_images_per_product])]
        product={"title":p.title,"descriptionHtml":p.description,"vendor":p.brand or self.client.settings.default_vendor or "","productType":p.category or "","status":"DRAFT","tags":tags,
                 "seo":{"title":p.title[:70],"description":seo},"metafields":[{"namespace":"source","key":"url","type":"url","value":str(p.source_url)}]}
        data=await self.client.execute(CREATE_PRODUCT,{"product":product,"media":media}); result=data["productCreate"]
        if result["userErrors"]: raise ShopifyUserError(result["userErrors"])
        created=result["product"]; variant=created["variants"]["nodes"][0]
        values={"id":variant["id"],"taxable":False}
        if price is not None: values["price"]=str(price)
        if p.compare_at_price is not None: values["compareAtPrice"]=str(p.compare_at_price)
        if p.sku or p.mpn: values["inventoryItem"]={"sku":p.sku or p.mpn}
        if p.barcode: values["barcode"]=p.barcode
        updated=await self.client.execute(UPDATE_VARIANTS,{"productId":created["id"],"variants":[values]})
        errors=updated["productVariantsBulkUpdate"]["userErrors"]
        if errors: raise ShopifyUserError(errors)
        forced=await self.client.execute(FORCE_DRAFT,{"product":{"id":created["id"],"status":"DRAFT"}})
        draft_result=forced["productUpdate"]
        if draft_result["userErrors"]: raise ShopifyUserError(draft_result["userErrors"])
        if draft_result["product"]["status"]!="DRAFT" or draft_result["product"]["publishedAt"]:
            raise ShopifyUserError([{"field":["status"],"message":"Shopify no confirmó el estado DRAFT"}])
        await ProductPublisher(self.client).prepare_online(created["id"])
        created["status"]="DRAFT"
        numeric=created["id"].rsplit("/",1)[-1]; store=self.client.settings.shopify_store_domain.split(".")[0]
        return created,f"https://admin.shopify.com/store/{store}/products/{numeric}"
