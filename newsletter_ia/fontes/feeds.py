"""Feeds RSS 2.0 / Atom de labs e newsletters (verificados em 2026-10-24).

Anthropic (Engineering e News) não tem feed: 404 em /engineering/rss.xml, /news/rss.xml e /rss.xml.
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from ..modelo import Item, data_ou_agora, item_id

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# (nome, url, fonte_tipo)
FEEDS = [
    ("deepmind", "https://deepmind.google/blog/rss.xml", "lab"),
    ("huggingface_blog", "https://huggingface.co/blog/feed.xml", "lab"),
    ("microsoft_research", "https://www.microsoft.com/en-us/research/feed/", "lab"),
    ("openai", "https://openai.com/news/rss.xml", "lab"),
    ("interconnects", "https://www.interconnects.ai/feed", "newsletter"),
    ("import_ai", "https://jack-clark.net/feed/", "newsletter"),
    ("latent_space", "https://www.latent.space/feed", "newsletter"),
]


def _data(valor):
    try:
        return parsedate_to_datetime(valor).isoformat()
    except (TypeError, ValueError):
        return data_ou_agora(valor)


def _txt(el, tag):
    f = el.find(tag)
    return (f.text or "").strip() if f is not None and f.text else ""


def coletar_feed(nome: str, url: str, fonte_tipo: str, desde: datetime, http_get=requests.get) -> list[Item]:
    resp = http_get(url, timeout=30)
    resp.raise_for_status()
    raiz = ET.fromstring(resp.text.encode("utf-8"))
    itens = []
    for e in raiz.iter("item"):
        link, data, resumo = _txt(e, "link"), _data(_txt(e, "pubDate")), _txt(e, "description")
        titulo = _txt(e, "title")
        itens.append((titulo, link, data, resumo))
    for e in raiz.iter(f"{ATOM_NS}entry"):
        a = e.find(f"{ATOM_NS}link")
        resumo = _txt(e, f"{ATOM_NS}summary")
        data = data_ou_agora(_txt(e, f"{ATOM_NS}published") or _txt(e, f"{ATOM_NS}updated"))
        itens.append((_txt(e, f"{ATOM_NS}title"), a.get("href", "") if a is not None else "", data, resumo))
    return [Item(item_id(link), nome, fonte_tipo, titulo, link, data, resumo)
            for titulo, link, data, resumo in itens
            if link and datetime.fromisoformat(data) >= desde]


def fontes(http_get=requests.get) -> dict:
    """Uma função de coleta por feed, para a falha de um não derrubar os outros."""
    def faz(nome, url, tipo):
        return lambda desde: coletar_feed(nome, url, tipo, desde, http_get)
    return {nome: faz(nome, url, tipo) for nome, url, tipo in FEEDS}
