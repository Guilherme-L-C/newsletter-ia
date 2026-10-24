import io
import json
import re
import tempfile
import subprocess
import unittest
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from newsletter_ia import coletar as coleta
from newsletter_ia import __main__ as cli
from newsletter_ia.config import MARGEM_DIAS
from newsletter_ia import db, pagina, selecao, triar, validacao
from newsletter_ia.fontes import arxiv, feeds, github, hf_papers, hn
from newsletter_ia.modelo import Item, data_ou_agora, item_id

UTC = timezone.utc
AGORA = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def novo_item(url="https://exemplo.com/a", fonte="arxiv", fonte_tipo="pesquisa", titulo="T", data=None):
    return Item(
        id=item_id(url),
        fonte=fonte,
        fonte_tipo=fonte_tipo,
        titulo=titulo,
        url=url,
        data_publicacao=(data or AGORA).isoformat(),
        resumo_bruto="",
    )


class Resp:
    def __init__(self, texto="", dados=None, status=200):
        self.text = texto
        self._dados = dados
        self.status_code = status

    def json(self):
        return self._dados

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


def http_fixo(resp):
    chamadas = []

    def http_get(url, params=None, **kw):
        chamadas.append((url, params))
        return resp

    http_get.chamadas = chamadas
    return http_get


ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2610.00001v1</id><title>Scaling LLM agents</title>
<summary>a</summary><published>2026-10-22T10:00:00Z</published></entry>
<entry><id>http://arxiv.org/abs/2610.00002v1</id><title>Crystal growth in alloys</title>
<summary>b</summary><published>2026-10-22T11:00:00Z</published></entry>
<entry><id>http://arxiv.org/abs/2610.00003v2</id><title>Graph colouring bounds</title>
<summary>c</summary></entry>
</feed>"""

HF_JSON = [
    {"paper": {"id": "2610.14224", "publishedAt": "2026-10-09T00:00:00.000Z"},
     "title": "Harness squared", "summary": "s", "publishedAt": "2026-10-08T20:00:00.000Z"},
]


class TestModeloData(unittest.TestCase):
    def test_data_ou_agora_converte_z(self):
        self.assertTrue(data_ou_agora("2026-10-09T00:00:00.000Z").startswith("2026-10-09T00:00:00"))

    def test_data_malformada_usa_hora_da_coleta(self):
        for ruim in (None, "", "lixo"):
            d = datetime.fromisoformat(data_ou_agora(ruim))
            self.assertLess(abs((datetime.now(UTC) - d).total_seconds()), 5)


class TestFontesPesquisa(unittest.TestCase):
    DESDE = datetime(2026, 10, 1, tzinfo=UTC)

    def test_hf_extrai_id_e_url(self):
        itens = hf_papers.coletar(self.DESDE, http_get=http_fixo(Resp(dados=HF_JSON)))
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0].url, "https://huggingface.co/papers/2610.14224")
        self.assertEqual(itens[0].fonte_tipo, "pesquisa")
        self.assertEqual(hf_papers.ids(itens), {"2610.14224"})

    def test_arxiv_filtra_por_termo_ou_hf(self):
        sleeps = []
        itens = arxiv.coletar(self.DESDE, {"2610.00002"}, http_get=http_fixo(Resp(texto=ATOM)),
                              sleep=sleeps.append)
        urls = sorted(i.url for i in itens)
        self.assertEqual(urls, ["https://arxiv.org/abs/2610.00001", "https://arxiv.org/abs/2610.00002"])

    def test_arxiv_espera_3s_entre_categorias_e_deduplica(self):
        sleeps = []
        itens = arxiv.coletar(self.DESDE, set(), http_get=http_fixo(Resp(texto=ATOM)), sleep=sleeps.append)
        self.assertEqual(sleeps, [3, 3, 3])
        self.assertEqual(len(itens), 1)

    def test_arxiv_item_sem_data_e_mantido(self):
        itens = arxiv.coletar(self.DESDE, {"2610.00003"}, http_get=http_fixo(Resp(texto=ATOM)),
                              sleep=lambda s: None)
        sem_data = [i for i in itens if i.url.endswith("2610.00003")]
        self.assertEqual(len(sem_data), 1)
        datetime.fromisoformat(sem_data[0].data_publicacao)

    def test_arxiv_descarta_anterior_a_desde(self):
        desde = datetime(2026, 10, 23, tzinfo=UTC)
        itens = arxiv.coletar(desde, {"2610.00002"}, http_get=http_fixo(Resp(texto=ATOM)), sleep=lambda s: None)
        self.assertEqual([i for i in itens if i.url.endswith("00001") or i.url.endswith("00002")], [])


HN_JSON = {"hits": [
    {"objectID": "111", "title": "Show HN: agente local", "url": None, "points": 120,
     "created_at": "2026-10-23T08:00:00Z", "created_at_i": 1792742400},
    {"objectID": "222", "title": "Novo paper sobre LLM", "url": "https://exemplo.com/p", "points": 300,
     "created_at": "2026-10-23T09:00:00Z", "created_at_i": 1792746000},
]}


class TestFontesComunidadeCodigo(unittest.TestCase):
    DESDE = datetime(2026, 10, 20, tzinfo=UTC)

    def test_hn_url_sem_link_usa_pagina_do_hn(self):
        itens = hn.coletar(self.DESDE, http_get=http_fixo(Resp(dados=HN_JSON)))
        urls = {i.url for i in itens}
        self.assertIn("https://news.ycombinator.com/item?id=111", urls)
        self.assertIn("https://exemplo.com/p", urls)

    def test_hn_deduplica_entre_termos(self):
        http = http_fixo(Resp(dados=HN_JSON))
        itens = hn.coletar(self.DESDE, http_get=http)
        self.assertGreater(len(http.chamadas), 1)
        self.assertEqual(len(itens), 2)

    def test_hn_filtra_por_pontos_e_data(self):
        http = http_fixo(Resp(dados=HN_JSON))
        hn.coletar(self.DESDE, http_get=http)
        filtros = http.chamadas[0][1]["numericFilters"]
        self.assertIn("points>=50", filtros)
        self.assertIn(f"created_at_i>={int(self.DESDE.timestamp())}", filtros)

    def test_github_descarta_salto_absurdo_de_estrelas(self):
        gh = {"items": [
            {"full_name": "x/suspeito", "html_url": "https://github.com/x/suspeito", "description": "d",
             "created_at": "2026-10-21T00:00:00Z", "pushed_at": "2026-10-24T00:00:00Z", "stargazers_count": 88243},
            {"full_name": "x/normal", "html_url": "https://github.com/x/normal", "description": "d",
             "created_at": "2026-10-21T00:00:00Z", "pushed_at": "2026-10-24T00:00:00Z", "stargazers_count": 400},
        ]}
        itens = github.coletar(self.DESDE, AGORA, http_get=http_fixo(Resp(dados=gh)))
        self.assertEqual([i.url for i in itens], ["https://github.com/x/normal"])

    def test_github_envia_qualificadores_e_deduplica(self):
        gh = {"items": [{"full_name": "x/normal", "html_url": "https://github.com/x/normal", "description": None,
                         "created_at": "2026-10-21T00:00:00Z", "pushed_at": "2026-10-24T00:00:00Z",
                         "stargazers_count": 400}]}
        http = http_fixo(Resp(dados=gh))
        itens = github.coletar(self.DESDE, AGORA, http_get=http)
        q = http.chamadas[0][1]["q"]
        self.assertIn("created:>=2026-10-20", q)
        self.assertIn("pushed:>=2026-09-24", q)
        self.assertEqual(len(itens), 1)


RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Post RSS</title><link>https://lab.exemplo/p1</link>
<pubDate>Thu, 22 Oct 2026 10:00:00 GMT</pubDate><description>resumo rss</description></item>
</channel></rss>"""

ATOM_FEED = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Post Atom</title><link href="https://lab.exemplo/p2"/>
<updated>2026-10-22T10:00:00Z</updated><summary>resumo atom</summary></entry></feed>"""


class TestFeedsEColeta(unittest.TestCase):
    DESDE = datetime(2026, 10, 1, tzinfo=UTC)

    def test_feeds_le_rss_e_atom(self):
        rss = feeds.coletar_feed("lab1", "https://x/rss", "lab", self.DESDE, http_get=http_fixo(Resp(texto=RSS)))
        atom = feeds.coletar_feed("lab2", "https://x/atom", "newsletter", self.DESDE,
                                  http_get=http_fixo(Resp(texto=ATOM_FEED)))
        self.assertEqual((rss[0].url, rss[0].fonte, rss[0].fonte_tipo, rss[0].titulo),
                         ("https://lab.exemplo/p1", "lab1", "lab", "Post RSS"))
        self.assertEqual((atom[0].url, atom[0].fonte_tipo), ("https://lab.exemplo/p2", "newsletter"))
        self.assertTrue(rss[0].data_publicacao.startswith("2026-10-22T10:00:00"))

    def test_fonte_que_falha_nao_derruba_as_outras(self):
        con = db.conectar(":memory:")

        def quebra(desde):
            import requests
            raise requests.HTTPError("HTTP 403")

        fontes = {"a": quebra, "b": lambda desde: [novo_item("https://x/1"), novo_item("https://x/2")]}
        resumo = coleta.coletar_tudo(con, AGORA, fontes)
        self.assertTrue(resumo["a"].startswith("falhou:") and "403" in resumo["a"])
        self.assertEqual(resumo["b"], "ok: 2 novos")
        self.assertEqual(con.execute("select count(*) from itens").fetchone()[0], 2)

    def test_falha_nao_avanca_a_ultima_coleta(self):
        con = db.conectar(":memory:")
        coleta.coletar_tudo(con, AGORA, {"a": lambda d: 1 / 0})
        self.assertIsNone(db.ultima_coleta(con, "a"))

    def test_primeira_coleta_usa_carga_inicial_e_seguinte_usa_ultima(self):
        con = db.conectar(":memory:")
        vistos = []
        fontes = {"a": lambda desde: vistos.append(desde) or []}
        coleta.coletar_tudo(con, AGORA, fontes)
        coleta.coletar_tudo(con, AGORA + timedelta(days=1), fontes)
        self.assertEqual(vistos, [AGORA - timedelta(days=7), AGORA - timedelta(days=MARGEM_DIAS)])

    def test_arxiv_recebe_ids_do_hf_na_coleta_padrao(self):
        def http_get(url, params=None, **kw):
            if "daily_papers" in url:
                recente = [{**HF_JSON[0], "publishedAt": "2026-10-23T08:00:00.000Z"}]
                return Resp(dados=recente)
            if "arxiv" in url:
                xml = ATOM.replace("2610.00003v2", "2610.14224v1")
                return Resp(texto=xml)
            return Resp(dados={"hits": [], "items": []}, texto=RSS)

        fontes = coleta.fontes_padrao(AGORA, http_get=http_get, sleep=lambda s: None)
        desde = AGORA - timedelta(days=7)
        fontes["hf_papers"](desde)
        urls = {i.url for i in fontes["arxiv"](desde)}
        self.assertIn("https://arxiv.org/abs/2610.14224", urls)  # fora do tema, entrou por estar no HF


def agy_saida(response, status="SUCCESS"):
    return SimpleNamespace(returncode=0, stderr="",
                           stdout=json.dumps({"status": status, "response": response, "conversation_id": "c"}))


def agy_que_aprova_tudo(chamadas):
    """Runner falso: devolve nota 7/tecnica para todo '- id=...' do prompt."""
    def runner(cmd, **kw):
        chamadas.append(cmd)
        prompt = cmd[cmd.index("-p") + 1]
        ids = re.findall(r"^- id=(\S+)", prompt, re.M)
        itens = [{"id": i, "nota": 7, "etiqueta": "tecnica", "motivo": "m"} for i in ids]
        return agy_saida(json.dumps({"itens": itens}))
    return runner


def popular(con, n):
    itens = [novo_item(f"https://x.com/{i}", titulo=f"T{i}") for i in range(n)]
    db.inserir_novos(con, itens, AGORA)
    return itens


class TestTriagemParse(unittest.TestCase):
    def test_parsear_aceita_bloco_de_codigo_e_objeto_itens(self):
        texto = '```json\n{"itens":[{"id":"a","nota":8,"etiqueta":"tecnica","motivo":"m"}]}\n```'
        r = triar.parsear_resposta(texto, {"a"})
        self.assertEqual(r, [triar.Triagem("a", 8, "tecnica", "m")])

    def test_parsear_aceita_lista_pura(self):
        r = triar.parsear_resposta('[{"id":"a","nota":1,"etiqueta":"descartar","motivo":"m"}]', {"a"})
        self.assertEqual(len(r), 1)

    def test_parsear_descarta_id_inventado(self):
        texto = json.dumps({"itens": [{"id": "zzz", "nota": 5, "etiqueta": "mercado", "motivo": "m"}]})
        self.assertEqual(triar.parsear_resposta(texto, {"a"}), [])

    def test_parsear_descarta_nota_fora_da_faixa_e_etiqueta_desconhecida(self):
        itens = [{"id": "a", "nota": 11, "etiqueta": "tecnica", "motivo": "m"},
                 {"id": "b", "nota": 7.5, "etiqueta": "tecnica", "motivo": "m"},
                 {"id": "c", "nota": 5, "etiqueta": "outra", "motivo": "m"},
                 {"id": "d", "nota": 5, "etiqueta": "mercado", "motivo": "m"}]
        r = triar.parsear_resposta(json.dumps(itens), {"a", "b", "c", "d"})
        self.assertEqual([x.id for x in r], ["d"])

    def test_parsear_levanta_em_texto_nao_json(self):
        with self.assertRaises(ValueError):
            triar.parsear_resposta("desculpe, não consegui", {"a"})


class TestChamarAgy(unittest.TestCase):
    def test_comando_usa_plan_e_schema_sem_pular_permissoes(self):
        cmds = []
        triar.chamar_agy("p", runner=lambda cmd, **kw: cmds.append(cmd) or agy_saida("[]"))
        cmd = cmds[0]
        self.assertEqual(cmd[:2], ["agy", "-p"])
        self.assertIn("plan", cmd)
        self.assertIn("--json-schema", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)

    def test_status_diferente_de_success_levanta(self):
        with self.assertRaises(triar.AgyErro):
            triar.chamar_agy("p", runner=lambda cmd, **kw: agy_saida("x", status="ERROR"))

    def test_timeout_e_codigo_de_saida_levantam(self):
        def estoura(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 1)
        with self.assertRaises(triar.AgyErro):
            triar.chamar_agy("p", runner=estoura)
        with self.assertRaises(triar.AgyErro):
            triar.chamar_agy("p", runner=lambda cmd, **kw: SimpleNamespace(returncode=2, stdout="", stderr=""))

    def test_devolve_o_campo_response(self):
        self.assertEqual(triar.chamar_agy("p", runner=lambda cmd, **kw: agy_saida("olá")), "olá")


class TestTriar(unittest.TestCase):
    def setUp(self):
        self.con = db.conectar(":memory:")

    def estados(self):
        return dict(self.con.execute("select estado, count(*) from itens group by estado").fetchall())

    def test_triar_respeita_teto_diario(self):
        popular(self.con, 200)
        chamadas = []
        r = triar.triar(self.con, AGORA, runner=agy_que_aprova_tudo(chamadas))
        self.assertEqual(self.estados(), {"triado": 150, "coletado": 50})
        self.assertEqual((r["triados"], r["adiados"], len(chamadas)), (150, 50, 10))

    def test_triar_desconta_o_que_ja_foi_triado_hoje(self):
        popular(self.con, 20)
        triar.triar(self.con, AGORA, runner=agy_que_aprova_tudo([]))
        popular_mais = [novo_item(f"https://y.com/{i}") for i in range(200)]
        db.inserir_novos(self.con, popular_mais, AGORA)
        triar.triar(self.con, AGORA, runner=agy_que_aprova_tudo([]))
        self.assertEqual(self.estados()["triado"], 150)

    def test_json_invalido_tenta_de_novo_uma_vez(self):
        popular(self.con, 3)
        bom = agy_que_aprova_tudo([])
        respostas = iter([agy_saida("lixo")])

        def runner(cmd, **kw):
            return next(respostas, None) or bom(cmd, **kw)

        r = triar.triar(self.con, AGORA, runner=runner)
        self.assertEqual((r["triados"], r["falhas"]), (3, 0))

    def test_resposta_invalida_nao_marca_triado(self):
        popular(self.con, 3)
        r = triar.triar(self.con, AGORA, runner=lambda cmd, **kw: agy_saida("lixo"))
        self.assertEqual(self.estados(), {"coletado": 3})
        self.assertEqual(r["falhas"], 1)

    def test_id_inventado_nao_grava_nada(self):
        popular(self.con, 1)
        falso = json.dumps({"itens": [{"id": "inventado", "nota": 9, "etiqueta": "tecnica", "motivo": "m"}]})
        triar.triar(self.con, AGORA, runner=lambda cmd, **kw: agy_saida(falso))
        self.assertEqual(self.estados(), {"coletado": 1})

    def test_para_no_primeiro_AgyErro(self):
        popular(self.con, 40)
        chamadas = []

        def runner(cmd, **kw):
            chamadas.append(cmd)
            return SimpleNamespace(returncode=1, stdout="", stderr="")

        r = triar.triar(self.con, AGORA, runner=runner)
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(r["triados"], 0)
        self.assertIsNotNone(r["erro"])

    def test_nota_e_etiqueta_gravadas(self):
        popular(self.con, 1)
        triar.triar(self.con, AGORA, runner=agy_que_aprova_tudo([]))
        row = self.con.execute("select nota, etiqueta, motivo, estado from itens").fetchone()
        self.assertEqual(tuple(row), (7, "tecnica", "m", "triado"))


def triado(con, url, fonte="arxiv", fonte_tipo="pesquisa", nota=7, etiqueta="tecnica", dias=1):
    it = novo_item(url, fonte=fonte, fonte_tipo=fonte_tipo, data=AGORA - timedelta(days=dias))
    db.inserir_novos(con, [it], AGORA)
    db.gravar_triagem(con, it.id, nota, etiqueta, "motivo", AGORA)
    return it.id


class TestSelecao(unittest.TestCase):
    def setUp(self):
        self.con = db.conectar(":memory:")

    def ids(self):
        return [c["id"] for c in selecao.candidatos(self.con, AGORA)]

    def test_candidatos_exclui_descartar_e_velhos(self):
        bom = triado(self.con, "https://x/bom")
        triado(self.con, "https://x/descartar", etiqueta="descartar", nota=1)
        triado(self.con, "https://x/velho", dias=15)
        self.assertEqual(self.ids(), [bom])

    def test_candidatos_limita_8_por_fonte_e_25_no_total(self):
        for f in ("a", "b", "c", "d"):
            for i in range(10):
                triado(self.con, f"https://x/{f}{i}", fonte=f, nota=i)
        cands = selecao.candidatos(self.con, AGORA)
        self.assertEqual(len(cands), 25)
        por_fonte = {}
        for c in cands:
            por_fonte[c["fonte"]] = por_fonte.get(c["fonte"], 0) + 1
        self.assertLessEqual(max(por_fonte.values()), 8)
        self.assertEqual([c["nota"] for c in cands], sorted((c["nota"] for c in cands), reverse=True))

    def test_candidatos_marca_marketing_de_lab(self):
        triado(self.con, "https://x/lab", fonte="openai", fonte_tipo="lab")
        triado(self.con, "https://x/arxiv")
        marketing = {c["fonte"]: c["marketing"] for c in selecao.candidatos(self.con, AGORA)}
        self.assertEqual(marketing, {"openai": True, "arxiv": False})

    def test_candidato_tem_os_campos_combinados(self):
        triado(self.con, "https://x/a")
        self.assertEqual(set(selecao.candidatos(self.con, AGORA)[0]),
                         {"id", "fonte", "fonte_tipo", "titulo", "url", "data", "etiqueta", "nota",
                          "motivo", "marketing"})

    def test_rascunhar_tira_item_dos_candidatos(self):
        i = triado(self.con, "https://x/a")
        self.assertEqual(selecao.rascunhar(self.con, [i]), 1)
        self.assertEqual(self.ids(), [])

    def test_reverter_devolve_item_aos_candidatos(self):
        i = triado(self.con, "https://x/a")
        selecao.rascunhar(self.con, [i])
        self.assertEqual(selecao.reverter(self.con, [i]), 1)
        self.assertEqual(self.ids(), [i])

    def test_publicar_so_a_partir_de_rascunhado(self):
        i = triado(self.con, "https://x/a")
        self.assertEqual(selecao.publicar(self.con, [i], AGORA), 0)
        self.assertEqual(self.con.execute("select estado from itens").fetchone()[0], "triado")

    def test_publicado_nao_volta_a_aparecer(self):
        i = triado(self.con, "https://x/a")
        selecao.rascunhar(self.con, [i])
        self.assertEqual(selecao.publicar(self.con, [i], AGORA), 1)
        self.assertEqual(self.ids(), [])
        self.assertEqual(selecao.reverter(self.con, [i]), 0)
        self.assertEqual(self.con.execute("select publicado_em from itens").fetchone()[0], AGORA.isoformat())

    def test_marcar_util(self):
        i = triado(self.con, "https://x/a")
        selecao.marcar_util(self.con, i, True)
        self.assertEqual(self.con.execute("select util from itens").fetchone()[0], 1)


class TestValidacao(unittest.TestCase):
    def setUp(self):
        self.con = db.conectar(":memory:")

    def test_amostra_cobre_faixa_de_notas_e_limita_por_fonte(self):
        for i in range(30):
            triado(self.con, f"https://x/{i}", fonte=f"f{i % 5}", nota=1 + i % 10)
        am = validacao.amostra(self.con, 20)
        self.assertEqual(len(am), 20)
        notas = [a["nota"] for a in am]
        self.assertEqual((min(notas), max(notas)), (1, 10))
        for f in range(5):
            self.assertLessEqual(sum(1 for a in am if a["fonte"] == f"f{f}"), 6)
        self.assertEqual(set(am[0]), {"id", "fonte", "titulo", "url", "nota", "etiqueta", "motivo"})

    def test_concordancia_calcula_fracao(self):
        a = triado(self.con, "https://x/a", nota=9)
        b = triado(self.con, "https://x/b", nota=2)
        c = triado(self.con, "https://x/c", nota=6)
        d = triado(self.con, "https://x/d", nota=8, etiqueta="descartar")
        rotulos = {a: "bom", b: "ruim", c: "ruim", d: "ruim"}
        self.assertEqual(validacao.concordancia(rotulos, self.con), 0.75)

    def test_concordancia_vazia_levanta(self):
        with self.assertRaises(ValueError):
            validacao.concordancia({}, self.con)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.con = db.conectar(":memory:")
        self.out = io.StringIO()

    def rodar(self, *argv, **kw):
        return cli.main(list(argv), agora=AGORA, con=self.con, out=self.out, **kw)

    def test_cli_candidatos_imprime_json_valido(self):
        i = triado(self.con, "https://x/a")
        self.assertEqual(self.rodar("candidatos"), 0)
        self.assertEqual([c["id"] for c in json.loads(self.out.getvalue())], [i])

    def test_cli_ciclo_rascunhado_publicado_reverter(self):
        i = triado(self.con, "https://x/a")
        self.rodar("publicado", i)
        self.assertEqual(self.con.execute("select estado from itens").fetchone()[0], "triado")
        self.rodar("rascunhado", i)
        self.rodar("reverter", i)
        self.assertEqual(self.con.execute("select estado from itens").fetchone()[0], "triado")
        self.rodar("rascunhado", i)
        self.rodar("publicado", i)
        self.assertEqual(self.con.execute("select estado from itens").fetchone()[0], "publicado")

    def test_cli_util(self):
        i = triado(self.con, "https://x/a")
        self.rodar("util", i, "nao")
        self.assertEqual(self.con.execute("select util from itens").fetchone()[0], 0)

    def test_cli_coletar_sai_com_codigo_1_se_fonte_falhou(self):
        code = self.rodar("coletar", fontes={"a": lambda d: 1 / 0, "b": lambda d: []})
        self.assertEqual(code, 1)
        self.assertIn("a: falhou", self.out.getvalue())
        self.assertIn("b: ok", self.out.getvalue())

    def test_cli_coletar_sai_com_0_se_tudo_ok(self):
        self.assertEqual(self.rodar("coletar", fontes={"b": lambda d: []}), 0)

    def test_cli_triar_sai_com_codigo_1_se_agy_falhar(self):
        popular(self.con, 2)
        runner = lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="")
        self.assertEqual(self.rodar("triar", runner=runner), 1)

    def test_cli_concordancia_passou_e_nao_passou(self):
        a = triado(self.con, "https://x/a", nota=9)
        b = triado(self.con, "https://x/b", nota=2)
        for rotulos, esperado in (({a: "bom", b: "ruim"}, "PASSOU"), ({a: "ruim", b: "bom"}, "NAO PASSOU")):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump(rotulos, f)
            self.out = io.StringIO()
            self.rodar("concordancia", f.name)
            saida = self.out.getvalue().strip()
            self.assertTrue(saida.endswith(esperado), saida)
            self.assertEqual("NAO" in saida, esperado.startswith("NAO"), saida)


class TestCorrecoesDaRevisao(unittest.TestCase):
    def test_segunda_coleta_ainda_ve_item_publicado_antes_da_primeira(self):
        """Revisão final, achado 1: arXiv/HF/HN mostram itens com atraso de 1 a 3 dias."""
        con = db.conectar(":memory:")
        publicado = AGORA - timedelta(days=3)  # antes da coleta anterior (AGORA - 2 dias)
        item = novo_item("https://arxiv.org/abs/2610.99999", data=publicado)
        fonte = lambda desde: [item] if publicado >= desde else []
        coleta.coletar_tudo(con, AGORA - timedelta(days=2), {"f": lambda d: []})
        resumo = coleta.coletar_tudo(con, AGORA, {"f": fonte})
        self.assertEqual(resumo["f"], "ok: 1 novos")

    def test_arxiv_pede_300_resultados_por_categoria(self):
        http = http_fixo(Resp(texto=ATOM))
        arxiv.coletar(datetime(2026, 10, 1, tzinfo=UTC), set(), http_get=http, sleep=lambda s: None)
        self.assertEqual(http.chamadas[0][1]["max_results"], 300)

    def test_mesmo_paper_no_hf_e_no_arxiv_tem_o_mesmo_id(self):
        """Achado 2: o paper não pode entrar duas vezes."""
        hf = hf_papers.coletar(datetime(2026, 10, 1, tzinfo=UTC), http_get=http_fixo(Resp(dados=HF_JSON)))[0]
        self.assertEqual(hf.id, item_id("https://arxiv.org/abs/2610.14224"))

    def test_item_id_normaliza_variantes_do_arxiv(self):
        base = item_id("https://arxiv.org/abs/2610.00001")
        for variante in ("http://arxiv.org/pdf/2610.00001v2", "https://arxiv.org/abs/2610.00001v3",
                         "https://www.arxiv.org/pdf/2610.00001v1.pdf"):
            self.assertEqual(item_id(variante), base, variante)

    def test_marketing_tambem_pelo_dominio_do_lab(self):
        """Achado 3: o mesmo post vindo do HN continua sendo blog do lab."""
        con = db.conectar(":memory:")
        triado(con, "https://openai.com/index/algo", fonte="hn", fonte_tipo="comunidade")
        triado(con, "https://exemplo.com/blog", fonte="hn", fonte_tipo="comunidade")
        marketing = {c["url"]: c["marketing"] for c in selecao.candidatos(con, AGORA)}
        self.assertEqual(marketing, {"https://openai.com/index/algo": True, "https://exemplo.com/blog": False})


def edicao(numero, data="2026-10-24", tema="Agentes que se verificam", titulo="Paper A"):
    return {"numero": numero, "data": data, "tema": tema, "nota": "nota da edição",
            "secoes": [{"titulo": "Técnicas e pesquisa", "itens": [
                {"titulo": titulo, "url": "https://arxiv.org/abs/1", "data": "2026-10-22", "fonte": "arxiv",
                 "porque": "porque sim", "marketing": False},
                {"titulo": "Post do lab", "url": "https://openai.com/x", "data": "2026-10-23", "fonte": "openai",
                 "porque": "p", "marketing": True}]}]}


class TestPagina(unittest.TestCase):
    def test_semana_mais_recente_primeiro(self):
        html = pagina.renderizar([edicao(1, tema="Tema um"), edicao(2, tema="Tema dois")])
        self.assertLess(html.index("Tema dois"), html.index("Tema um"))
        self.assertIn("Semana 2", html)

    def test_item_tem_link_data_e_porque(self):
        html = pagina.renderizar([edicao(1)])
        self.assertIn('href="https://arxiv.org/abs/1"', html)
        self.assertIn("22/10/2026", html)
        self.assertIn("porque sim", html)

    def test_marca_blog_do_lab(self):
        self.assertIn("blog do próprio lab", pagina.renderizar([edicao(1)]))

    def test_texto_externo_e_escapado(self):
        html = pagina.renderizar([edicao(1, titulo='<script>alert(1)</script>')])
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)

    def test_salvar_edicao_grava_json_e_regenera_index(self):
        pasta = Path(tempfile.mkdtemp())
        pagina.salvar_edicao(edicao(1), pasta)
        pagina.salvar_edicao(edicao(2, tema="Outro tema"), pasta)
        self.assertTrue((pasta / "edicoes" / "semana-001.json").exists())
        index = (pasta / "index.html").read_text()
        self.assertIn("Outro tema", index)
        self.assertIn("Agentes que se verificam", index)

    def test_salvar_mesma_semana_substitui(self):
        pasta = Path(tempfile.mkdtemp())
        pagina.salvar_edicao(edicao(1, tema="Velho"), pasta)
        pagina.salvar_edicao(edicao(1, tema="Novo"), pasta)
        index = (pasta / "index.html").read_text()
        self.assertIn("Novo", index)
        self.assertNotIn("Velho", index)


class TestBanco(unittest.TestCase):
    def setUp(self):
        self.con = db.conectar(":memory:")

    def test_item_id_ignora_fragmento_e_barra_final(self):
        self.assertEqual(item_id("https://A.com/x/#y"), item_id("https://a.com/x"))

    def test_inserir_novos_ignora_repetido(self):
        a = novo_item("https://exemplo.com/a", fonte="arxiv")
        b = novo_item("https://exemplo.com/a", fonte="hn")
        self.assertEqual(db.inserir_novos(self.con, [a], AGORA), 1)
        self.assertEqual(db.inserir_novos(self.con, [b], AGORA), 0)
        n = self.con.execute("select count(*) from itens").fetchone()[0]
        self.assertEqual(n, 1)

    def test_ultima_coleta_none_ate_registrar(self):
        self.assertIsNone(db.ultima_coleta(self.con, "arxiv"))
        db.registrar_coleta(self.con, "arxiv", AGORA)
        self.assertEqual(db.ultima_coleta(self.con, "arxiv"), AGORA)


if __name__ == "__main__":
    unittest.main()
