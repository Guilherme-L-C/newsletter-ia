"""Validação inicial: amostra para Guilherme classificar e concordância com a nota do agy."""

from .config import NOTA_CORTE_BOM

MAX_POR_FONTE_AMOSTRA = 6


def amostra(con, n: int = 20) -> list[dict]:
    rows = con.execute("select id, fonte, titulo, url, nota, etiqueta, motivo from itens"
                       " where estado='triado' order by nota, id").fetchall()
    usados: set[int] = set()
    por_fonte: dict[str, int] = {}
    escolhidos = []
    for k in range(min(n, len(rows))):
        alvo = round(k * (len(rows) - 1) / max(n - 1, 1))
        for desvio in sorted(range(-len(rows), len(rows)), key=abs):  # do mais perto para o mais longe
            j = alvo + desvio
            if 0 <= j < len(rows) and j not in usados and por_fonte.get(rows[j]["fonte"], 0) < MAX_POR_FONTE_AMOSTRA:
                usados.add(j)
                por_fonte[rows[j]["fonte"]] = por_fonte.get(rows[j]["fonte"], 0) + 1
                escolhidos.append(dict(rows[j]))
                break
    return escolhidos


def concordancia(rotulos: dict[str, str], con) -> float:
    acordos = total = 0
    for id, rotulo in rotulos.items():
        row = con.execute("select nota, etiqueta from itens where id=?", (id,)).fetchone()
        if row is None or row["nota"] is None:
            continue
        agy_bom = row["nota"] >= NOTA_CORTE_BOM and row["etiqueta"] != "descartar"
        acordos += agy_bom == (rotulo == "bom")
        total += 1
    if not total:
        raise ValueError("nenhum rótulo corresponde a um item triado")
    return acordos / total
