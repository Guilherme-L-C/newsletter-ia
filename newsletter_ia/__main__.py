"""CLI: python3 -m newsletter_ia <comando>."""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime

from . import coletar as coleta
from . import db, selecao, triar, validacao
from .config import CONCORDANCIA_MIN


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newsletter_ia")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nome in ("coletar", "triar", "candidatos", "amostra"):
        sub.add_parser(nome)
    for nome in ("rascunhado", "publicado", "reverter"):
        sub.add_parser(nome).add_argument("ids", nargs="+")
    u = sub.add_parser("util")
    u.add_argument("id")
    u.add_argument("valor", choices=("sim", "nao"))
    sub.add_parser("concordancia").add_argument("arquivo")
    return p


def main(argv: list[str], agora: datetime | None = None, con=None, out=None, fontes=None,
         runner=subprocess.run) -> int:
    out = out or sys.stdout
    agora = agora or datetime.now(UTC)
    args = _parser().parse_args(argv)
    con = con or db.conectar()

    def say(texto):
        print(texto, file=out)

    if args.cmd == "coletar":
        resumo = coleta.coletar_tudo(con, agora, fontes or coleta.fontes_padrao(agora))
        for nome, r in resumo.items():
            say(f"{nome}: {r}")
        return 1 if any(r.startswith("falhou") for r in resumo.values()) else 0
    if args.cmd == "triar":
        r = triar.triar(con, agora, runner=runner)
        say(json.dumps(r, ensure_ascii=False))
        return 1 if r["erro"] else 0
    if args.cmd == "candidatos":
        say(json.dumps(selecao.candidatos(con, agora), ensure_ascii=False, separators=(",", ":")))
    elif args.cmd == "amostra":
        say(json.dumps(validacao.amostra(con), ensure_ascii=False, separators=(",", ":")))
    elif args.cmd == "rascunhado":
        say(f"{selecao.rascunhar(con, args.ids)} itens em rascunho")
    elif args.cmd == "publicado":
        say(f"{selecao.publicar(con, args.ids, agora)} itens publicados")
    elif args.cmd == "reverter":
        say(f"{selecao.reverter(con, args.ids)} itens revertidos")
    elif args.cmd == "util":
        selecao.marcar_util(con, args.id, args.valor == "sim")
        say("ok")
    elif args.cmd == "concordancia":
        with open(args.arquivo) as f:
            c = validacao.concordancia(json.load(f), con)
        say(f"{c:.2f} {'PASSOU' if c >= CONCORDANCIA_MIN else 'NAO PASSOU'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
