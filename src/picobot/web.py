"""Pagine web (articoli, blog): scarica e estrae il testo principale. Deterministico, nessun LLM.

Solo http/https verso indirizzi pubblici: localhost, rete privata e metadata cloud sono rifiutati, anche dopo un
redirect (altrimenti chi usa il bot potrebbe fargli leggere servizi interni). Il testo resta DATO NON FIDATO.
Senza proxy si verifica anche l'IP a cui la connessione e' arrivata (DNS rebinding); con un proxy il nome lo
risolve il proxy, che deve quindi negare da se' le destinazioni private.
"""
import asyncio
import ipaddress
import re
import urllib.request

import httpx
import trafilatura

from .documents import DocumentError

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_S = 20
MAX_REDIRECTS = 5
_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PicoBot)", "Accept": "text/html,application/xhtml+xml"}


def is_url(text: str) -> bool:
    return bool(_URL.match(text.strip()))


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    return [i[4][0] for i in infos]


async def _check_public(url: httpx.URL) -> None:
    try:
        host, shown = url.raw_host.decode("ascii"), url.host   # raw_host: il nome a cui httpx si collega (IDNA2008)
    except UnicodeError:
        raise DocumentError("Link non valido.") from None
    if url.scheme not in ("http", "https") or not host:
        raise DocumentError("Link non valido: serve un indirizzo http:// o https://.")
    try:
        ips = [str(ipaddress.ip_address(host))]
    except ValueError:  # nome, non IP
        try:
            ips = await _resolve(host)
        except (OSError, UnicodeError):
            raise DocumentError(f"Impossibile scaricare la pagina: host {shown} sconosciuto.") from None
    if not ips or not all(_is_public(ip) for ip in ips):
        raise DocumentError("Indirizzo non consentito (rete locale o privata).")


def _is_public(ip: str) -> bool:
    return ipaddress.ip_address(ip.split("%")[0]).is_global


def _via_proxy(url: httpx.URL) -> bool:
    """Stesse variabili che legge httpx (HTTP(S)_PROXY, ALL_PROXY, NO_PROXY)."""
    proxies = urllib.request.getproxies_environment()
    return bool(proxies.get(url.scheme) or proxies.get("all")) and not urllib.request.proxy_bypass_environment(url.host)


def _landed_on_public_ip(r: httpx.Response) -> bool:
    stream = r.extensions.get("network_stream")
    addr = stream.get_extra_info("server_addr") if stream is not None else None
    return bool(addr) and _is_public(str(addr[0]))


async def fetch_article(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Ritorna il testo principale dell'articolo; ogni problema esce come DocumentError con un messaggio chiaro."""
    try:
        target = httpx.URL(url.strip())
    except (httpx.InvalidURL, UnicodeError):
        raise DocumentError("Link non valido.") from None
    try:
        async with asyncio.timeout(TIMEOUT_S):   # tetto complessivo: i timeout di httpx valgono per singola lettura
            html = await _download(target, transport)
    except TimeoutError:
        raise DocumentError(f"Pagina troppo lenta (oltre {TIMEOUT_S} s).") from None
    text = await asyncio.to_thread(trafilatura.extract, html, include_comments=False, include_tables=True)
    if not text or not text.strip():
        raise DocumentError("Nessun articolo leggibile nella pagina.")
    return text.strip()


async def _download(target: httpx.URL, transport: httpx.AsyncBaseTransport | None) -> str | bytes:
    async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT_S, headers=_HEADERS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _check_public(target)          # a ogni salto: un redirect non porta in rete privata
            try:
                async with client.stream("GET", target) as r:
                    if not _via_proxy(target) and not _landed_on_public_ip(r):   # prima di leggere qualsiasi cosa
                        raise DocumentError("Indirizzo non consentito (rete locale o privata).")
                    if r.is_redirect and r.headers.get("location"):
                        target = target.join(r.headers["location"])
                        continue
                    if r.status_code >= 400:
                        raise DocumentError(f"Impossibile scaricare la pagina (HTTP {r.status_code}).")
                    if "html" not in r.headers.get("content-type", "").lower():
                        raise DocumentError("Il link non è una pagina HTML: riassumo solo articoli e blog.")
                    body = bytearray()
                    async for chunk in r.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            raise DocumentError(f"Pagina troppo grande (max {MAX_BYTES // 1024 // 1024} MB).")
                    # senza charset nell'header lo decide trafilatura dai byte (anche dal <meta charset>)
                    return body.decode(r.encoding, errors="replace") if r.charset_encoding else bytes(body)
            except httpx.HTTPError as e:
                raise DocumentError(f"Impossibile scaricare la pagina ({type(e).__name__}).") from e
    raise DocumentError("Troppi redirect.")
