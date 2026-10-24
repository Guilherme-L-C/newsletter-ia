"""GitHub: busca de repositórios novos e ativos (não há endpoint de trending)."""

from datetime import datetime, timedelta

import requests

from ..config import GITHUB_ATIVIDADE_DIAS, GITHUB_ESTRELAS_SUSPEITO
from ..modelo import Item, data_ou_agora, item_id

URL = "https://api.github.com/search/repositories"
TOPICOS = ("llm", "ai-agents", "machine-learning")


def coletar(desde: datetime, agora: datetime, http_get=requests.get) -> list[Item]:
    ativo_desde = (agora - timedelta(days=GITHUB_ATIVIDADE_DIAS)).date().isoformat()
    vistos: dict[str, Item] = {}
    for topico in TOPICOS:
        q = f"topic:{topico} created:>={desde.date().isoformat()} pushed:>={ativo_desde}"
        resp = http_get(URL, params={"q": q, "sort": "stars", "order": "desc", "per_page": 30},
                        headers={"Accept": "application/vnd.github+json"}, timeout=30)
        resp.raise_for_status()
        for r in resp.json()["items"]:
            nome = r["full_name"]
            criado = datetime.fromisoformat(data_ou_agora(r.get("created_at")))
            if nome in vistos or (r["stargazers_count"] > GITHUB_ESTRELAS_SUSPEITO
                                  and agora - criado < timedelta(days=7)):
                continue
            vistos[nome] = Item(item_id(r["html_url"]), "github", "codigo", nome, r["html_url"],
                                criado.isoformat(), (r.get("description") or "").strip())
    return list(vistos.values())
