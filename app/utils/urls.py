import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class UnsafeUrlError(ValueError):
    pass


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Solo se permiten URLs HTTP/HTTPS públicas")
    query = [(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(query), ""))


def _public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return ip.is_global


def validate_public_url(url: str, resolver=socket.getaddrinfo) -> str:
    safe = normalize_url(url)
    host = urlsplit(safe).hostname or ""
    if host.lower() == "localhost" or host.endswith(".local"):
        raise UnsafeUrlError("Destino local bloqueado")
    try:
        if not _public_ip(host):
            raise UnsafeUrlError("Dirección IP no pública bloqueada")
    except ValueError:
        try:
            addresses = {item[4][0] for item in resolver(host, 443, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise UnsafeUrlError("No se pudo resolver el dominio") from exc
        if not addresses or any(not _public_ip(ip) for ip in addresses):
            raise UnsafeUrlError("El dominio resuelve a una red no pública")
    return safe

