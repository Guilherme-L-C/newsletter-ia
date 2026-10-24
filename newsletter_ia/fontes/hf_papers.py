"""Hugging Face Daily Papers (API pública, sem token)."""

import re
from datetime import datetime

import requests

from ..modelo import Item, data_ou_agora, item_id

URL = "https://huggingface.co/api/daily_papers"


def coletar(desde: datetime, http_get=requests.get) -> list[Item]:
    resp = http_get(URL, params={"limit": 100, "sort": "trending"}, timeout=30)
    resp.raise_for_status()
    itens = []
    for e in resp.json():
        paper_id = e["paper"]["id"]
        data = data_ou_agora(e.get("publishedAt") or e["paper"].get("publishedAt"))
        if datetime.fromisoformat(data) < desde:
            continue
        url = f"https://huggingface.co/papers/{paper_id}"
        # id do arXiv: o mesmo paper vindo do HF e do arXiv é um item só
        itens.append(Item(item_id(f"https://arxiv.org/abs/{paper_id}"), "hf_papers", "pesquisa", e.get("title", "").strip(), url, data,
                          e.get("summary", "").strip()))
    return itens


def ids(itens: list[Item]) -> set[str]:
    return {m.group(1) for i in itens if (m := re.search(r"/papers/(.+)$", i.url))}
