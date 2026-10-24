"""Caminhos e constantes da newsletter de IA (config e estado fora do Syncthing)."""

import json
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "state" / "newsletter-ia"
CONFIG_PATH = Path.home() / ".config" / "newsletter-ia" / "config.json"
DB_PATH = STATE_DIR / "itens.db"
AGY_CWD = STATE_DIR / "agy-cwd"
# Página das edições: na vault, para abrir no navegador e sincronizar com o Mac.
EDICOES_DIR = Path.home() / "segundo-cerebro" / "01-Projetos" / "newsletter-ia"

JANELA_DIAS = 14
MAX_POR_FONTE = 8
N_CANDIDATOS = 25
TETO_AGY_DIA = 150
CARGA_INICIAL_DIAS = 7
MARGEM_DIAS = 4
LOTE_AGY = 15
HN_PONTOS_MIN = 50
GITHUB_ATIVIDADE_DIAS = 30
GITHUB_ESTRELAS_SUSPEITO = 20000
CONCORDANCIA_MIN = 0.70
NOTA_CORTE_BOM = 6

ETIQUETAS = ("tecnica", "mercado", "repositorio", "decisao-projeto", "descartar")


def load() -> dict:
    cfg = json.loads(CONFIG_PATH.read_text())
    return {"destinatario": cfg["destinatario"]}
