"""Coleta diária: roda cada fonte isolada, grava itens novos e a data da última coleta."""

import time
from collections.abc import Callable
from datetime import datetime, timedelta

import requests

from . import db
from .config import CARGA_INICIAL_DIAS, MARGEM_DIAS
from .fontes import arxiv, feeds, github, hf_papers, hn
from .modelo import Item


def coletar_tudo(con, agora: datetime, fontes: dict[str, Callable[[datetime], list[Item]]]) -> dict[str, str]:
    resumo = {}
    for nome, coletar in fontes.items():
        ultima = db.ultima_coleta(con, nome)
        # Margem: arXiv, HF e HN mostram itens com 1 a 3 dias de atraso; a dedupe por id torna a sobreposição gratuita.
        desde = ultima - timedelta(days=MARGEM_DIAS) if ultima else agora - timedelta(days=CARGA_INICIAL_DIAS)
        try:
            itens = coletar(desde)
        except Exception as e:  # uma fonte fora do ar não derruba as outras
            resumo[nome] = f"falhou: {e}"
            continue
        resumo[nome] = f"ok: {db.inserir_novos(con, itens, agora)} novos"
        db.registrar_coleta(con, nome, agora)
    return resumo


def fontes_padrao(agora: datetime, http_get=requests.get, sleep=time.sleep) -> dict[str, Callable]:
    """HF roda antes do arXiv, que usa os ids dos papers do HF como sinal de relevância."""
    ids_hf: set[str] = set()

    def hf(desde):
        itens = hf_papers.coletar(desde, http_get)
        ids_hf.update(hf_papers.ids(itens))
        return itens

    return {
        "hf_papers": hf,
        "arxiv": lambda desde: arxiv.coletar(desde, ids_hf, http_get, sleep),
        "hn": lambda desde: hn.coletar(desde, http_get),
        "github": lambda desde: github.coletar(desde, agora, http_get),
        **feeds.fontes(http_get),
    }
