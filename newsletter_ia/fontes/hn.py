"""Hacker News via Algolia (search_by_date, sem chave)."""

from datetime import datetime

import requests

from ..config import HN_PONTOS_MIN
from ..modelo import Item, data_ou_agora, item_id

URL = "https://hn.algolia.com/api/v1/search_by_date"
TERMOS = ("LLM", "AI agent", "language model", "Claude", "Gemini")


def coletar(desde: datetime, http_get=requests.get) -> list[Item]:
    vistos: dict[str, Item] = {}
    for termo in TERMOS:
        resp = http_get(URL, params={
            "query": termo, "tags": "story", "hitsPerPage": 50,
            "numericFilters": f"points>={HN_PONTOS_MIN},created_at_i>={int(desde.timestamp())}",
        }, timeout=30)
        resp.raise_for_status()
        for h in resp.json()["hits"]:
            oid = h["objectID"]
            if oid in vistos:
                continue
            url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
            vistos[oid] = Item(item_id(url), "hn", "comunidade", (h.get("title") or "").strip(), url,
                               data_ou_agora(h.get("created_at")), "")
    return list(vistos.values())
