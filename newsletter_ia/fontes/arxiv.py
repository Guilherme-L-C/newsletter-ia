"""arXiv (API Atom, https, 3 s entre chamadas)."""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from ..modelo import Item, data_ou_agora, item_id

URL = "https://export.arxiv.org/api/query"
CATEGORIAS = ("cs.LG", "cs.CL", "cs.MA", "cs.AI")
TERMOS_IA = ("llm", "language model", "agent", "transformer", "reinforcement", "diffusion",
             "alignment", "retrieval")
NS = {"a": "http://www.w3.org/2005/Atom"}


def _texto(e, tag):
    el = e.find(f"a:{tag}", NS)
    return " ".join((el.text or "").split()) if el is not None else ""


def coletar(desde: datetime, ids_hf: set[str], http_get=requests.get, sleep=time.sleep) -> list[Item]:
    vistos: dict[str, Item] = {}
    for n, cat in enumerate(CATEGORIAS):
        if n:
            sleep(3)
        resp = http_get(URL, params={"search_query": f"cat:{cat}", "sortBy": "submittedDate",
                                     "sortOrder": "descending", "max_results": 300}, timeout=60)
        resp.raise_for_status()
        for e in ET.fromstring(resp.text).findall("a:entry", NS):
            arxiv_id = re.sub(r"v\d+$", "", _texto(e, "id").rsplit("/abs/", 1)[-1])
            titulo = _texto(e, "title")
            if arxiv_id in vistos or not (arxiv_id in ids_hf or any(t in titulo.lower() for t in TERMOS_IA)):
                continue
            data = data_ou_agora(_texto(e, "published"))
            if datetime.fromisoformat(data) < desde:
                continue
            url = f"https://arxiv.org/abs/{arxiv_id}"
            vistos[arxiv_id] = Item(item_id(url), "arxiv", "pesquisa", titulo, url, data, _texto(e, "summary"))
    return list(vistos.values())
