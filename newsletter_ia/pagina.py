"""Página HTML local com todas as edições, uma seção por semana (a mais recente no topo)."""

import json
from html import escape
from pathlib import Path

CSS = """
:root{--bg:#f7f5f0;--fg:#1f1d1a;--muted:#6b665e;--card:#fff;--line:#e4dfd5;--accent:#b4441f;--tag:#efe9dd}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece8e1;--muted:#a39d93;--card:#1f1e1b;--line:#33302b;--accent:#f0875f;--tag:#2a2824}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 Georgia,'Times New Roman',serif}
.wrap{max-width:760px;margin:0 auto;padding:40px 16px 80px}
header.capa{border-bottom:3px double var(--line);padding-bottom:18px;margin-bottom:28px}
header.capa h1{font-size:44px;line-height:1.1;margin:0;letter-spacing:-.5px}
header.capa p{color:var(--muted);margin:6px 0 0;font-family:system-ui,sans-serif;font-size:14px}
nav{font-family:system-ui,sans-serif;font-size:14px;margin-bottom:32px}nav a{color:var(--accent);margin-right:14px}
section.semana{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:26px 24px;margin-bottom:36px}
.semana .rotulo{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:var(--accent)}
.semana h2{font-size:30px;line-height:1.2;margin:4px 0 4px}
.semana .data{font-family:system-ui,sans-serif;color:var(--muted);font-size:14px;margin:0 0 18px}
.semana h3{font-family:system-ui,sans-serif;font-size:13px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);border-top:1px solid var(--line);padding-top:16px;margin:24px 0 8px}
article{margin:0 0 18px}article a.titulo{color:var(--fg);font-weight:bold;text-decoration:none;border-bottom:1px solid var(--accent)}
article a.titulo:hover{color:var(--accent)}
.meta{font-family:system-ui,sans-serif;font-size:13px;color:var(--muted)}
.tag{display:inline-block;background:var(--tag);border-radius:4px;padding:0 6px;margin-left:6px;font-size:12px}
article p{margin:4px 0 0}.nota{font-family:system-ui,sans-serif;font-size:13px;color:var(--muted);margin-top:20px}
"""


def _data_br(iso: str) -> str:
    a, m, d = iso[:10].split("-")
    return f"{d}/{m}/{a}"


def _item(it: dict) -> str:
    tag = '<span class="tag">blog do próprio lab</span>' if it.get("marketing") else ""
    return (f'<article><a class="titulo" href="{escape(it["url"])}">{escape(it["titulo"])}</a>'
            f'<div class="meta">{_data_br(it["data"])} · {escape(it.get("fonte", ""))}{tag}</div>'
            f'<p><b>Por que importa:</b> {escape(it["porque"])}</p></article>')


def _semana(ed: dict) -> str:
    secoes = "".join(f'<h3>{escape(s["titulo"])}</h3>' + "".join(_item(i) for i in s["itens"])
                     for s in ed["secoes"])
    nota = f'<p class="nota">{escape(ed["nota"])}</p>' if ed.get("nota") else ""
    return (f'<section class="semana" id="semana-{ed["numero"]}"><div class="rotulo">Semana {ed["numero"]}</div>'
            f'<h2>{escape(ed["tema"])}</h2><p class="data">{_data_br(ed["data"])}</p>{secoes}{nota}</section>')


def renderizar(edicoes: list[dict]) -> str:
    eds = sorted(edicoes, key=lambda e: e["numero"], reverse=True)
    nav = "".join(f'<a href="#semana-{e["numero"]}">Semana {e["numero"]}</a>' for e in eds)
    return ("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>Newsletter IA</title><style>{CSS}</style></head><body><div class=\"wrap\">"
            "<header class=\"capa\"><h1>Newsletter IA</h1><p>Direto das fontes: labs, arXiv, GitHub, "
            "Hacker News e Hugging Face.</p></header>"
            f"<nav>{nav}</nav>{''.join(_semana(e) for e in eds)}</div></body></html>")


def salvar_edicao(edicao: dict, pasta: Path) -> Path:
    dados = pasta / "edicoes"
    dados.mkdir(parents=True, exist_ok=True)
    (dados / f"semana-{edicao['numero']:03d}.json").write_text(json.dumps(edicao, ensure_ascii=False, indent=2))
    edicoes = [json.loads(p.read_text()) for p in sorted(dados.glob("semana-*.json"))]
    index = pasta / "index.html"
    index.write_text(renderizar(edicoes))
    return index
