def media_summary(product):
    return [{"id":x["id"],"status":x.get("status"),"alt":x.get("alt")} for x in product.get("media",{}).get("nodes",[])]
