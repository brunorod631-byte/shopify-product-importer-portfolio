import ipaddress
import re
from urllib.parse import urljoin, urlsplit

import httpx
from playwright.async_api import async_playwright

from app.services.image_service import process_image

IMAGE_ATTRS = ("src", "data-src", "data-lazy-src", "data-original", "data-zoom", "srcset")
REJECT = re.compile(r"logo|icon|sprite|avatar|banner|placeholder|loading|spinner|whatsapp|facebook|instagram|pixel|tracking", re.I)


def _public_https(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def choose_srcset(value: str) -> str:
    candidates=[]
    for part in (value or "").split(","):
        bits=part.strip().split()
        if not bits: continue
        weight=0
        if len(bits)>1:
            match=re.match(r"([\d.]+)(w|x)",bits[-1])
            if match: weight=float(match.group(1))*(1000 if match.group(2)=="x" else 1)
        candidates.append((weight,bits[0]))
    return max(candidates,default=(0,""))[1]


async def rendered_image_candidates(url: str, timeout_seconds: int, max_bytes: int, limit: int) -> list[str]:
    candidates=[]
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch(headless=True)
        try:
            context=await browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),locale="es-UY",
            )
            page=await context.new_page()
            await page.goto(url,wait_until="domcontentloaded",timeout=timeout_seconds*1000)
            try: await page.wait_for_load_state("networkidle",timeout=min(10_000,timeout_seconds*1000))
            except Exception: pass
            selectors='meta[property="og:image"],meta[name="twitter:image"],img,source'
            for element in await page.locator(selectors).all():
                values=[]
                content=await element.get_attribute("content")
                if content: values.append(content)
                for attr in IMAGE_ATTRS:
                    value=await element.get_attribute(attr)
                    if value: values.append(choose_srcset(value) if attr=="srcset" else value)
                for value in values:
                    absolute=urljoin(page.url,value)
                    if _public_https(absolute) and not REJECT.search(absolute) and absolute not in candidates:
                        candidates.append(absolute)
            backgrounds=await page.locator('[style*="background-image"]').evaluate_all(
                "els => els.map(e => getComputedStyle(e).backgroundImage)"
            )
            for style in backgrounds:
                match=re.search(r'url\\(["\\\']?(.*?)["\\\']?\\)',style or "")
                if match:
                    absolute=urljoin(page.url,match.group(1))
                    if _public_https(absolute) and not REJECT.search(absolute) and absolute not in candidates:
                        candidates.append(absolute)
        finally:
            await browser.close()
    valid=[]
    headers={"User-Agent":"ShopifyTelegramImporter/1.0","Referer":url,"Accept":"image/*"}
    async with httpx.AsyncClient(timeout=timeout_seconds,follow_redirects=True,headers=headers) as client:
        for candidate in candidates[:30]:
            try:
                response=await client.get(candidate)
                if response.status_code==200 and response.headers.get("content-type","").lower().startswith("image/") and len(response.content)<=max_bytes and process_image(response.content):
                    valid.append(str(response.url))
                    if len(valid)>=limit: break
            except httpx.HTTPError: continue
    return valid
