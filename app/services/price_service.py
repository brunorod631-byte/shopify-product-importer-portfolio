from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup

from app.utils.money import apply_markup


def final_price(price: Decimal|None, markup: float, currency: str|None):
    return None if price is None else apply_markup(price, markup, Decimal("1") if currency=="UYU" else Decimal("0.01"))


class ExchangeRateError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurrencyConversion:
    original_amount: Decimal
    original_currency: str
    amount_uyu: Decimal
    rate: Decimal
    rate_date: str


class CurrencyConverter:
    def __init__(self, settings):
        self.settings = settings
        self._cache: dict[str, tuple[datetime, Decimal, str]] = {}

    async def convert_to_uyu(self, amount: Decimal, currency: str | None) -> CurrencyConversion:
        if not currency:
            raise ExchangeRateError(
                "La fuente publicó un precio sin indicar moneda; edite el precio manualmente en UYU"
            )
        source = currency.upper()
        if source == "UYU":
            return CurrencyConversion(amount, source, amount, Decimal("1"), "local")
        now = datetime.now(timezone.utc)
        cached = self._cache.get(source)
        if cached and cached[0] > now:
            rate, date = cached[1], cached[2]
        else:
            url = self.settings.exchange_rate_api_url.format(currency=source)
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.get(url, headers={"User-Agent": "ShopifyTelegramImporter/1.0"})
            response.raise_for_status()
            payload = response.json()
            try:
                rate = Decimal(str(payload["rates"]["UYU"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ExchangeRateError(f"No hay cotización {source}/UYU disponible") from exc
            if rate <= 0:
                raise ExchangeRateError(f"Cotización {source}/UYU inválida")
            date = str(payload.get("time_last_update_utc") or payload.get("time_last_update_unix") or "actual")
            expires = now + timedelta(hours=self.settings.exchange_rate_cache_hours)
            self._cache[source] = (expires, rate, date)
        converted = (amount * rate).quantize(Decimal("0.01"))
        return CurrencyConversion(amount, source, converted, rate, date)

    async def convert_to_uyu_brou(self, amount: Decimal, currency: str | None) -> CurrencyConversion:
        if not currency:
            raise ExchangeRateError("INGCO publicó un precio sin moneda; edite el precio manualmente en UYU")
        source=currency.upper()
        if source=="UYU": return CurrencyConversion(amount,source,amount,Decimal("1"),"BROU - moneda local")
        cache_key=f"BROU:{source}";now=datetime.now(timezone.utc);cached=self._cache.get(cache_key)
        if cached and cached[0]>now:
            rate,date=cached[1],cached[2]
        else:
            url=("https://www.brou.com.uy/c/portal/render_portlet?"
                 "p_l_id=20593&p_p_id=cotizacionfull_WAR_broutmfportlet_INSTANCE_otHfewh1klyS&"
                 "p_p_lifecycle=0&p_t_lifecycle=0&p_p_state=normal&p_p_mode=view&"
                 "p_p_col_id=column-1&p_p_col_pos=0&p_p_col_count=2&p_p_isolated=1&currentURL=%2Fcotizaciones")
            try:
                async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                    response=await client.get(url,headers={"User-Agent":"ShopifyTelegramImporter/1.0","Referer":"https://www.brou.com.uy/cotizaciones","Accept":"text/html"})
                response.raise_for_status();rate=parse_brou_rate(response.text,source)
            except (httpx.HTTPError,ValueError) as exc:
                raise ExchangeRateError(f"No se pudo obtener la cotización de venta {source}/UYU del BROU") from exc
            date=f"BROU venta — consulta {now.astimezone().strftime('%d/%m/%Y %H:%M')}"
            self._cache[cache_key]=(now+timedelta(hours=self.settings.exchange_rate_cache_hours),rate,date)
        return CurrencyConversion(amount,source,(amount*rate).quantize(Decimal("0.01")),rate,date)


BROU_CURRENCIES={"USD":"Dólar","EUR":"Euro","ARS":"Peso Argentino","BRL":"Real","GBP":"Libra Esterlina","CHF":"Franco Suizo"}

def parse_brou_number(value: str) -> Decimal:
    return Decimal(value.strip().replace(".","").replace(",","."))

def parse_brou_rate(html: str,currency: str) -> Decimal:
    expected=BROU_CURRENCIES.get(currency.upper())
    if not expected: raise ValueError("Moneda no disponible en BROU")
    soup=BeautifulSoup(html,"lxml")
    for row in soup.select("tbody tr"):
        name=row.select_one(".moneda")
        if not name or name.get_text(" ",strip=True)!=expected: continue
        values=[x.get_text(" ",strip=True) for x in row.select("p.valor") if x.get_text(" ",strip=True)]
        if len(values)<2: break
        rate=parse_brou_number(values[1])
        if rate<=0: break
        return rate
    raise ValueError(f"Cotización {currency} no encontrada en BROU")
