"""SQLite da newsletter: itens coletados, triados e publicados."""

import sqlite3
from datetime import datetime
from pathlib import Path

from .config import DB_PATH
from .modelo import Item

SCHEMA = """
create table if not exists itens (
    id text primary key,
    fonte text not null,
    fonte_tipo text not null,
    titulo text not null,
    url text not null,
    data_publicacao text not null,
    data_coleta text not null,
    resumo_bruto text not null default '',
    estado text not null default 'coletado',
    nota integer,
    etiqueta text,
    motivo text,
    data_triagem text,
    publicado_em text,
    util integer
);
create table if not exists coletas (
    fonte text primary key,
    ate text not null
);
"""


def conectar(path: Path | str = DB_PATH) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def inserir_novos(con, itens: list[Item], agora: datetime) -> int:
    n = 0
    for it in itens:
        cur = con.execute(
            "insert or ignore into itens (id, fonte, fonte_tipo, titulo, url, data_publicacao,"
            " data_coleta, resumo_bruto) values (?,?,?,?,?,?,?,?)",
            (it.id, it.fonte, it.fonte_tipo, it.titulo, it.url, it.data_publicacao,
             agora.isoformat(), it.resumo_bruto),
        )
        n += cur.rowcount
    con.commit()
    return n


def ultima_coleta(con, fonte: str) -> datetime | None:
    row = con.execute("select ate from coletas where fonte=?", (fonte,)).fetchone()
    return datetime.fromisoformat(row["ate"]) if row else None


def registrar_coleta(con, fonte: str, ate: datetime) -> None:
    con.execute("insert or replace into coletas (fonte, ate) values (?,?)", (fonte, ate.isoformat()))
    con.commit()


def pendentes_triagem(con, limite: int) -> list[Item]:
    rows = con.execute(
        "select id, fonte, fonte_tipo, titulo, url, data_publicacao, resumo_bruto from itens"
        " where estado='coletado' order by data_publicacao desc limit ?", (limite,)).fetchall()
    return [Item(*tuple(r)) for r in rows]


def gravar_triagem(con, id: str, nota: int, etiqueta: str, motivo: str, agora: datetime) -> None:
    con.execute("update itens set estado='triado', nota=?, etiqueta=?, motivo=?, data_triagem=? where id=?",
                (nota, etiqueta, motivo, agora.isoformat(), id))
    con.commit()


def triados_hoje(con, hoje) -> int:
    return con.execute("select count(*) from itens where substr(data_triagem,1,10)=?",
                       (hoje.isoformat(),)).fetchone()[0]
