"""Candidatos da edição e transições de estado dos itens."""

from datetime import datetime, timedelta

from .config import JANELA_DIAS, MAX_POR_FONTE, N_CANDIDATOS

# Post de lab é marcado mesmo quando chega por outra fonte (ex.: HN).
DOMINIOS_LAB = ("openai.com", "anthropic.com", "deepmind.google", "deepmind.com", "blog.google",
                "huggingface.co/blog", "microsoft.com/en-us/research", "ai.meta.com", "mistral.ai")


def candidatos(con, agora: datetime) -> list[dict]:
    corte = (agora - timedelta(days=JANELA_DIAS)).isoformat()
    rows = con.execute(
        """select * from (
             select *, row_number() over (partition by fonte order by nota desc, data_publicacao desc) as pos
             from itens
             where estado='triado' and etiqueta != 'descartar' and data_publicacao >= ?
           ) where pos <= ? order by nota desc, data_publicacao desc limit ?""",
        (corte, MAX_POR_FONTE, N_CANDIDATOS)).fetchall()
    return [{"id": r["id"], "fonte": r["fonte"], "fonte_tipo": r["fonte_tipo"], "titulo": r["titulo"],
             "url": r["url"], "data": r["data_publicacao"], "etiqueta": r["etiqueta"], "nota": r["nota"],
             "motivo": r["motivo"], "marketing": r["fonte_tipo"] == "lab" or any(d in r["url"] for d in DOMINIOS_LAB)} for r in rows]


def _transicao(con, ids: list[str], de: str, para: str, extra: str = "", args: tuple = ()) -> int:
    n = 0
    for i in ids:
        n += con.execute(f"update itens set estado=?{extra} where id=? and estado=?",
                         (para, *args, i, de)).rowcount
    con.commit()
    return n


def rascunhar(con, ids: list[str]) -> int:
    return _transicao(con, ids, "triado", "rascunhado")


def publicar(con, ids: list[str], agora: datetime) -> int:
    return _transicao(con, ids, "rascunhado", "publicado", ", publicado_em=?", (agora.isoformat(),))


def reverter(con, ids: list[str]) -> int:
    return _transicao(con, ids, "rascunhado", "triado")


def marcar_util(con, id: str, util: bool) -> None:
    con.execute("update itens set util=? where id=?", (1 if util else 0, id))
    con.commit()
