> **Nota (2026-10-24):** cópia da nota do mesmo nome na vault (`segundo-cerebro/01-Projetos/`). O código saiu de `00-Sistema/scripts/newsletter_ia/` e agora mora **neste repositório** (`~/newsletter-ia`). Caminhos antigos abaixo valem como histórico.

# Newsletter IA — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coletar fontes de IA por API todo dia, triar com o `agy` e deixar candidatos prontos para o Claude montar, sob demanda, a edição semanal (~10 itens) como rascunho no Gmail.

**Architecture:** Pacote Python `newsletter_ia` em `00-Sistema/scripts/`. Um timer diário roda `coletar` (APIs → SQLite) e outro roda `triar` (lotes ao `agy -p` → nota/etiqueta). O Claude, pela skill `montar-edicao`, roda `candidatos`, escolhe, escreve, cria o rascunho no Gmail e atualiza os estados pelo mesmo CLI.

**Tech Stack:** Python 3.12 (`/usr/bin/python3`, stdlib + `requests` 2.31, já instalado; sem `feedparser`), `sqlite3`, `unittest`, `agy` CLI, systemd user units.

**Spec:** `01-Projetos/Newsletter IA - Design.md`

## Global Constraints
- Cofre não é git: **sem passo de commit**.
- Código em `~/segundo-cerebro/00-Sistema/scripts/newsletter_ia/`; testes em `tests/test_newsletter_ia.py` (um arquivo, como `test_telegram_relay.py`). Rodar: `cd ~/segundo-cerebro/00-Sistema/scripts && python3 -m unittest tests.test_newsletter_ia -v`.
- Banco: `~/.local/state/newsletter-ia/itens.db`. Config (destinatário, fora do Syncthing): `~/.config/newsletter-ia/config.json` = `{"destinatario": "..."}`.
- Estados do item: `coletado` → `triado` → `rascunhado` → `publicado`; `reverter` volta `rascunhado` para `triado`. Itens nunca são apagados.
- Etiquetas: `tecnica`, `mercado`, `repositorio`, `decisao-projeto`, `descartar`. Nota inteira de 0 a 10.
- Constantes (todas em `config.py`): `JANELA_DIAS=14`, `MAX_POR_FONTE=8`, `N_CANDIDATOS=25`, `TETO_AGY_DIA=150`, `CARGA_INICIAL_DIAS=7`, `LOTE_AGY=15`, `HN_PONTOS_MIN=50`, `GITHUB_ATIVIDADE_DIAS=30`, `GITHUB_ESTRELAS_SUSPEITO=20000`, `CONCORDANCIA_MIN=0.70`, `NOTA_CORTE_BOM=6`. Os valores `HN_PONTOS_MIN`, `GITHUB_ESTRELAS_SUSPEITO` e `NOTA_CORTE_BOM` são palpites do plano, não do Design; ajustáveis.
- `fonte_tipo` ∈ `pesquisa` (arXiv, HF), `comunidade` (HN), `codigo` (GitHub), `lab` (blogs/feeds de labs), `newsletter`. Marcação de marketing = `fonte_tipo == "lab"`.
- arXiv: `https://export.arxiv.org/api/query` (https), 3 s entre chamadas, resposta Atom/XML. GitHub: `GET /search/repositories`, 10 req/min sem login. HF: `GET https://huggingface.co/api/daily_papers?limit=100&sort=trending`. HN: `https://hn.algolia.com/api/v1/search_by_date`.
- Chamada ao `agy`: `agy -p <prompt> --output-format json --mode plan` (+ `--json-schema` se a Task 1 confirmar), `cwd` neutro `~/.local/state/newsletter-ia/agy-cwd`, nunca `--dangerously-skip-permissions`, nunca dado pessoal no prompt. Resposta do `agy` é um JSON com `status`, `response`, `conversation_id` (padrão de `telegram_relay/agy.py`); `status != "SUCCESS"` é falha.
- Só o próprio Guilherme recebe algo. A edição é **rascunho** no Gmail, nunca envio automático.
- Funções que fazem rede/subprocesso recebem o chamador por parâmetro (`http_get`, `runner`, `sleep`) para teste sem rede.
- Timers/serviços em `~/.config/systemd/user/`, no padrão de `coletor.service`/`coletor.timer`; fuso America/Recife.

## Review Focus
1. **Fonte fora do ar, 403 ou XML quebrado** → as outras fontes seguem e o resumo da coleta marca a falha (teste na Task 5).
2. **Mesma URL vinda de duas fontes ou de duas coletas** → um item só (teste na Task 2).
3. **Resposta do `agy` com JSON inválido, id inventado, nota fora de 0–10 ou etiqueta desconhecida** → nada é gravado errado; o item continua `coletado` (teste na Task 6).
4. **Primeira carga grande** → no máximo `TETO_AGY_DIA` itens vão ao `agy` por dia; o excedente fica `coletado` para o dia seguinte (teste na Task 6).
5. **Rascunho descartado** → `reverter` devolve os itens a `triado` e eles voltam a aparecer em `candidatos` (teste na Task 7).
6. **Item sem data de publicação ou com data malformada** → usa a data da coleta, sem derrubar a coleta (teste na Task 3).

## Estrutura de arquivos
- `newsletter_ia/__init__.py`, `__main__.py` — CLI (`python3 -m newsletter_ia <comando>`).
- `config.py` — caminhos, constantes, `load()`.
- `modelo.py` — `Item` e `item_id`.
- `db.py` — esquema SQLite e operações sobre itens/coletas.
- `fontes/arxiv.py`, `fontes/hf_papers.py`, `fontes/hn.py`, `fontes/github.py`, `fontes/feeds.py` — uma por fonte.
- `coletar.py` — orquestra as fontes com isolamento de falha.
- `triar.py` — prompt, chamada ao `agy`, parse e gravação.
- `selecao.py` — `candidatos` e transições de estado.
- `validacao.py` — itens de amostra e concordância.
- `~/.claude/skills/montar-edicao/SKILL.md` — skill do Claude.
- `~/.config/systemd/user/newsletter-ia-{coletar,triar}.{service,timer}`.

---

### Task 1: Sondar o `agy` (verificação, sem código)

**Files:** nenhum arquivo do pacote; anotar o resultado em `Newsletter IA - Design.md`, seção "O que fica para quem construir".

**Produces:** a decisão `USAR_JSON_SCHEMA: bool` e a latência real por lote, que a Task 6 consome.

- [ ] **Step 1:** Rodar uma chamada mínima e olhar a saída:
  `cd /tmp && agy -p 'Devolva só o JSON [{"id":"a","nota":5}]' --output-format json --mode plan`
  Esperado: JSON de saída com `status: "SUCCESS"` e `response` contendo o texto.
- [ ] **Step 2:** Repetir com `--json-schema '{"type":"array","items":{"type":"object","required":["id","nota"],"properties":{"id":{"type":"string"},"nota":{"type":"integer"}}}}'`. Esperado: `response` já é JSON válido do schema. Se o flag falhar ou o `response` vier com texto em volta, registrar `USAR_JSON_SCHEMA = False`.
- [ ] **Step 3:** Cronometrar um lote de 15 itens fictícios (título + 2 linhas) pedindo nota/etiqueta. Registrar o tempo; se passar de 4 min, reduzir `LOTE_AGY` para 10.
- [ ] **Step 4:** Escrever os três resultados (flag funciona?, tempo por lote, `LOTE_AGY` final) na seção do Design.

### Task 2: Banco e modelo

**Files:**
- Create: `newsletter_ia/__init__.py`, `config.py`, `modelo.py`, `db.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Produces:
  - `modelo.Item` (dataclass frozen): `id, fonte, fonte_tipo, titulo, url, data_publicacao, resumo_bruto` (todos `str`; `data_publicacao` ISO 8601 UTC).
  - `modelo.item_id(url: str) -> str` — `sha1` hex dos primeiros 16 caracteres da URL normalizada (minúscula, sem `#fragmento`, sem `/` final).
  - `db.conectar(path: Path = DB_PATH) -> sqlite3.Connection` — cria tabelas `itens(id PK, fonte, fonte_tipo, titulo, url, data_publicacao, data_coleta, resumo_bruto, estado, nota, etiqueta, motivo, data_triagem, publicado_em, util)` e `coletas(fonte PK, ate)`.
  - `db.inserir_novos(con, itens: list[Item], agora: datetime) -> int` — ignora `id` já existente, devolve quantos entraram, estado `coletado`.
  - `db.ultima_coleta(con, fonte: str) -> datetime | None`; `db.registrar_coleta(con, fonte: str, ate: datetime) -> None`.

- [ ] **Step 1: Testes** `test_item_id_ignora_fragmento_e_barra_final` (`item_id("https://A.com/x/#y") == item_id("https://a.com/x")`), `test_inserir_novos_ignora_repetido` (inserir a mesma URL de duas fontes → retorno 1 e depois 0, uma linha só), `test_ultima_coleta_none_ate_registrar`.
- [ ] **Step 2:** Rodar; esperado FAIL (módulos não existem).
- [ ] **Step 3:** Implementar `config.py` (constantes e `load() -> dict` lendo `CONFIG_PATH`), `modelo.py`, `db.py` com as assinaturas acima. `conectar(":memory:")` deve funcionar nos testes.
- [ ] **Step 4:** Rodar; esperado PASS.

### Task 3: Fontes de pesquisa (HF Daily Papers e arXiv)

**Files:**
- Create: `newsletter_ia/fontes/__init__.py`, `fontes/hf_papers.py`, `fontes/arxiv.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Consumes: `modelo.Item`, `modelo.item_id`, `config.CARGA_INICIAL_DIAS`.
- Produces:
  - `hf_papers.coletar(desde: datetime, http_get=requests.get) -> list[Item]` — `fonte="hf_papers"`, `fonte_tipo="pesquisa"`, URL `https://huggingface.co/papers/<id>`.
  - `hf_papers.ids(itens: list[Item]) -> set[str]` — ids de arXiv (`2610.14224`) extraídos das URLs.
  - `arxiv.coletar(desde: datetime, ids_hf: set[str], http_get=requests.get, sleep=time.sleep) -> list[Item]` — categorias `cs.LG`, `cs.CL`, `cs.MA`, `cs.AI`, `sortBy=submittedDate` descendente, `fonte="arxiv"`, `fonte_tipo="pesquisa"`, `sleep(3)` entre categorias. Entra só se `id in ids_hf` **ou** o título contém um de `TERMOS_IA = ("llm","language model","agent","transformer","reinforcement","diffusion","alignment","retrieval")` (comparação minúscula).

- [ ] **Step 1: Testes** com respostas falsas: `test_hf_extrai_id_e_url` (JSON mínimo → `Item.url == "https://huggingface.co/papers/2610.14224"`), `test_arxiv_filtra_por_termo_ou_hf` (3 entradas Atom: uma com "LLM" no título, uma fora do tema, uma fora do tema mas com id em `ids_hf` → 2 itens), `test_arxiv_espera_3s_entre_categorias` (`sleep` falso chamado com 3), `test_data_malformada_usa_hora_da_coleta` (Review Focus 6: entrada sem `<published>` ou com data inválida → o item é mantido e `data_publicacao` recebe a hora UTC atual).
- [ ] **Step 2:** Rodar; esperado FAIL.
- [ ] **Step 3:** Implementar parse do Atom com `xml.etree.ElementTree` (namespace `http://www.w3.org/2005/Atom`). Itens com `data_publicacao` anterior a `desde` são descartados; sem data ou data inválida → o campo recebe a hora UTC atual (ISO 8601) e o item é mantido. Essa regra vale para todas as fontes; implementar como função única `modelo.data_ou_agora(valor: str | None) -> str`.
- [ ] **Step 4:** Rodar; esperado PASS.
- [ ] **Step 5 (verificação real):** `python3 -c "from newsletter_ia.fontes import hf_papers; import datetime as d; print(len(hf_papers.coletar(d.datetime.now(d.UTC)-d.timedelta(days=7))))"` → inteiro > 0.

### Task 4: Fontes de comunidade e código (HN e GitHub)

**Files:**
- Create: `newsletter_ia/fontes/hn.py`, `fontes/github.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Consumes: `modelo.Item`, `config.HN_PONTOS_MIN`, `config.GITHUB_ATIVIDADE_DIAS`, `config.GITHUB_ESTRELAS_SUSPEITO`.
- Produces:
  - `hn.coletar(desde: datetime, http_get=requests.get) -> list[Item]` — Algolia `search_by_date`, `tags=story`, `numericFilters=points>=HN_PONTOS_MIN,created_at_i>=<desde>`, uma consulta por termo de `("LLM","AI agent","language model","Claude","Gemini")`; `fonte="hn"`, `fonte_tipo="comunidade"`; URL = `url` do story, ou `https://news.ycombinator.com/item?id=<objectID>` se não houver.
  - `github.coletar(desde: datetime, agora: datetime, http_get=requests.get) -> list[Item]` — consultas `topic:llm`, `topic:ai-agents`, `topic:machine-learning` com `created:>=<desde>` e `pushed:>=<agora - GITHUB_ATIVIDADE_DIAS>`, `sort=stars`, `per_page=30`; `fonte="github"`, `fonte_tipo="codigo"`; descarta repositório com `stargazers_count > GITHUB_ESTRELAS_SUSPEITO` criado há menos de 7 dias.

- [ ] **Step 1: Testes** `test_hn_url_sem_link_usa_pagina_do_hn`, `test_hn_deduplica_entre_termos` (mesmo `objectID` em dois termos → um item), `test_github_descarta_salto_absurdo_de_estrelas` (repo com 88243 estrelas criado há 3 dias é excluído; repo com 400 estrelas entra), `test_github_envia_qualificadores` (a query enviada contém `created:>=` e `pushed:>=`).
- [ ] **Step 2:** Rodar; esperado FAIL.
- [ ] **Step 3:** Implementar. Erro HTTP (`raise_for_status`) propaga como exceção; a Task 5 isola.
- [ ] **Step 4:** Rodar; esperado PASS.

### Task 5: Feeds dos labs e orquestrador de coleta

**Files:**
- Create: `newsletter_ia/fontes/feeds.py`, `coletar.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Consumes: `db.conectar`, `db.inserir_novos`, `db.ultima_coleta`, `db.registrar_coleta`, todas as `coletar` das Tasks 3 e 4, `config.CARGA_INICIAL_DIAS`.
- Produces:
  - `feeds.FEEDS: list[tuple[str, str, str]]` — `(nome, url, fonte_tipo)`; `feeds.coletar(desde: datetime, http_get=requests.get) -> list[Item]` — lê RSS 2.0 ou Atom, uma fonte por feed (`fonte=nome`).
  - `coletar.coletar_tudo(con, agora: datetime, fontes: dict[str, Callable[[datetime], list[Item]]]) -> dict[str, str]` — para cada fonte: `desde = ultima_coleta(fonte) or agora - CARGA_INICIAL_DIAS`; em sucesso grava itens e `registrar_coleta(fonte, agora)` e devolve `"ok: N novos"`; em exceção **não** registra a coleta e devolve `"falhou: <mensagem>"`; nunca propaga.

- [ ] **Step 1 (verificação real dos feeds):** para cada candidato, `curl -sL -o /dev/null -w "%{http_code} %{content_type}\n" <url>` e manter em `FEEDS` só os que dão 200 e XML: DeepMind `https://deepmind.google/blog/rss.xml`, Hugging Face `https://huggingface.co/blog/feed.xml`, Microsoft Research `https://www.microsoft.com/en-us/research/feed/`, OpenAI `https://openai.com/news/rss.xml`, Interconnects `https://www.interconnects.ai/feed`, Import AI `https://jack-clark.net/feed/`, Latent Space `https://www.latent.space/feed`, e tentar feeds de Anthropic Engineering/News. Tipos: labs → `lab`; as três newsletters → `newsletter`. **Anthropic Engineering e release notes sem feed confirmado ficam fora da v1** — registrar na seção "O que fica para quem construir" do Design (desvio consciente em relação à lista de fontes).
- [ ] **Step 2: Testes** `test_feeds_le_rss_e_atom`, `test_fonte_que_falha_nao_derruba_as_outras` (uma fonte levanta `requests.HTTPError`, outra devolve 2 itens → resumo `{"a": "falhou: ...", "b": "ok: 2 novos"}` e os 2 itens no banco), `test_falha_nao_avanca_a_ultima_coleta`, `test_primeira_coleta_usa_carga_inicial` (`desde` recebido = `agora - 7 dias`), `test_coleta_seguinte_usa_ultima_coleta`.
- [ ] **Step 3:** Rodar; esperado FAIL. Implementar. Rodar; esperado PASS.

### Task 6: Triagem pelo `agy`

**Files:**
- Create: `newsletter_ia/triar.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Consumes: `db.pendentes_triagem`, `db.gravar_triagem`, `db.triados_hoje`, `config.TETO_AGY_DIA`, `config.LOTE_AGY`, `config.ETIQUETAS`, a decisão `USAR_JSON_SCHEMA` e o `LOTE_AGY` da Task 1.
- Produces:
  - `db.pendentes_triagem(con, limite: int) -> list[Item]` (estado `coletado`, mais recentes primeiro), `db.gravar_triagem(con, id: str, nota: int, etiqueta: str, motivo: str, agora: datetime) -> None` (estado `triado`, `data_triagem`), `db.triados_hoje(con, hoje: date) -> int`.
  - `triar.Triagem` (dataclass): `id: str, nota: int, etiqueta: str, motivo: str`.
  - `triar.montar_prompt(itens: list[Item]) -> str` — instrui: relevância para quem quer **aprender técnicas** (peso maior), depois mercado, repositório e decisão de projeto; devolver só JSON `[{"id","nota","etiqueta","motivo"}]`; inclui dois exemplos fixos de calibração (um item com nota 9 e um com nota 2) marcados como exemplos, fora do lote; pede `motivo` de uma linha.
  - `triar.parsear_resposta(texto: str, ids_esperados: set[str]) -> list[Triagem]` — aceita JSON puro ou dentro de bloco ```; descarta entradas com id fora de `ids_esperados`, nota fora de 0–10 ou não inteira, etiqueta fora de `ETIQUETAS`; levanta `ValueError` se o texto inteiro não for JSON.
  - `triar.chamar_agy(prompt: str, timeout: int = 600, runner=subprocess.run) -> str` — devolve o campo `response`; levanta `AgyErro(Exception)` em timeout, código ≠ 0, JSON de saída inválido ou `status != "SUCCESS"`.
  - `triar.triar(con, agora: datetime, runner=subprocess.run) -> dict` — `{"triados": int, "falhas": int, "adiados": int}`. Respeita `TETO_AGY_DIA - triados_hoje`; processa em lotes de `LOTE_AGY`; em `ValueError` tenta o lote **uma vez mais**, depois conta falha e segue; `AgyErro` interrompe a execução (não gasta cota à toa) e devolve o que já fez.

- [ ] **Step 1: Testes** `test_parsear_aceita_bloco_de_codigo`, `test_parsear_descarta_id_inventado` (Review Focus 3), `test_parsear_descarta_nota_fora_da_faixa_e_etiqueta_desconhecida`, `test_parsear_levanta_em_texto_nao_json`, `test_chamar_agy_status_diferente_de_success_levanta`, `test_triar_respeita_teto_diario` (200 itens `coletado`, `triados_hoje=0` → exatamente 150 viram `triado`, 50 continuam `coletado`; Review Focus 4), `test_triar_json_invalido_tenta_de_novo_uma_vez` (runner devolve lixo e depois JSON válido → itens triados, `falhas == 0`), `test_resposta_invalida_nao_marca_triado` (dois lixos seguidos → itens seguem `coletado`, `falhas == 1`), `test_triar_para_ao_primeiro_AgyErro`.
- [ ] **Step 2:** Rodar; esperado FAIL.
- [ ] **Step 3:** Implementar. Comando do `agy` conforme Global Constraints; criar o `cwd` neutro se não existir.
- [ ] **Step 4:** Rodar; esperado PASS.
- [ ] **Step 5 (verificação real):** inserir 5 itens reais com `coletar` e rodar `triar` uma vez; conferir no SQLite que os 5 têm `nota`, `etiqueta` e `motivo`, e que o `motivo` bate com o título.

### Task 7: Seleção e estados

**Files:**
- Create: `newsletter_ia/selecao.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Consumes: `db.conectar`, `config.JANELA_DIAS`, `config.MAX_POR_FONTE`, `config.N_CANDIDATOS`.
- Produces:
  - `selecao.candidatos(con, agora: datetime) -> list[dict]` — itens com estado `triado`, etiqueta ≠ `descartar`, `data_publicacao` dentro de `JANELA_DIAS`; ordenados por `nota` desc; no máximo `MAX_POR_FONTE` por `fonte`; no máximo `N_CANDIDATOS` no total. Cada dict: `id, fonte, fonte_tipo, titulo, url, data, etiqueta, nota, motivo, marketing: bool` (`marketing = fonte_tipo == "lab"`).
  - `selecao.rascunhar(con, ids: list[str]) -> int`, `selecao.publicar(con, ids: list[str], agora: datetime) -> int`, `selecao.reverter(con, ids: list[str]) -> int`, `selecao.marcar_util(con, id: str, util: bool) -> None`. Cada transição só vale a partir do estado anterior correto (`rascunhar`: `triado`; `publicar`: `rascunhado`; `reverter`: `rascunhado`) e devolve quantos itens mudaram.

- [ ] **Step 1: Testes** `test_candidatos_exclui_descartar_e_velhos`, `test_candidatos_limita_8_por_fonte_e_25_no_total`, `test_candidatos_marca_marketing_de_lab`, `test_rascunhar_tira_item_dos_candidatos`, `test_reverter_devolve_item_aos_candidatos` (Review Focus 5), `test_publicar_so_a_partir_de_rascunhado` (item `triado` → retorno 0, estado igual), `test_publicado_nao_volta_a_aparecer`.
- [ ] **Step 2:** Rodar; esperado FAIL. Implementar. Rodar; esperado PASS.

### Task 8: Validação inicial (amostra e concordância)

**Files:**
- Create: `newsletter_ia/validacao.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Consumes: `config.CONCORDANCIA_MIN`, `config.NOTA_CORTE_BOM`.
- Produces:
  - `validacao.amostra(con, n: int = 20) -> list[dict]` — `n` itens `triado` espalhados pela faixa de notas (ordenar por nota e pegar posições igualmente espaçadas), sem repetir `fonte` mais de 6 vezes; dict com `id, fonte, titulo, url, nota, etiqueta, motivo`.
  - `validacao.concordancia(rotulos: dict[str, str], con) -> float` — `rotulos` mapeia `id → "bom" | "ruim"`; o `agy` conta como "bom" se `nota >= NOTA_CORTE_BOM` e etiqueta ≠ `descartar`; devolve a fração de acordos. Levanta `ValueError` se `rotulos` estiver vazio.

- [ ] **Step 1: Testes** `test_amostra_cobre_faixa_de_notas` (itens com notas 1..10 → amostra inclui nota mínima e máxima), `test_concordancia_calcula_fracao` (4 rótulos, 3 acordos → `0.75`), `test_concordancia_vazia_levanta`.
- [ ] **Step 2:** Rodar; esperado FAIL. Implementar. Rodar; esperado PASS.

### Task 9: CLI

**Files:**
- Create: `newsletter_ia/__main__.py`
- Test: `tests/test_newsletter_ia.py`

**Interfaces:**
- Consumes: tudo acima.
- Produces: `main(argv: list[str], agora: datetime | None = None) -> int`, com os comandos: `coletar` (imprime o resumo por fonte), `triar` (imprime o dict), `candidatos` (JSON compacto de `selecao.candidatos`), `rascunhado ID...`, `publicado ID...`, `reverter ID...`, `util ID sim|nao`, `amostra` (JSON de `validacao.amostra`), `concordancia ARQUIVO.json` (imprime a fração e `PASSOU`/`NAO PASSOU` contra `CONCORDANCIA_MIN`). Código de saída 0 em sucesso; ≠ 0 se alguma fonte falhou ou `triar` terminou por `AgyErro`.

- [ ] **Step 1: Testes** `test_cli_candidatos_imprime_json_valido`, `test_cli_publicado_so_a_partir_de_rascunhado`, `test_cli_coletar_sai_com_codigo_1_se_fonte_falhou`, `test_cli_concordancia_passou_e_nao_passou` (0.75 → `PASSOU`; 0.5 → `NAO PASSOU`).
- [ ] **Step 2:** Rodar; esperado FAIL. Implementar com `argparse`. Rodar; esperado PASS.
- [ ] **Step 3 (verificação real):** `cd ~/segundo-cerebro/00-Sistema/scripts && python3 -m newsletter_ia coletar` → uma linha por fonte; pelo menos HF, arXiv e HN com `ok`. Depois `python3 -m newsletter_ia candidatos` → `[]` (nada triado ainda) sem erro.

### Task 10: Timers systemd (criados, não ligados)

**Files:**
- Create: `~/.config/systemd/user/newsletter-ia-coletar.service`, `newsletter-ia-coletar.timer`, `newsletter-ia-triar.service`, `newsletter-ia-triar.timer`

**Interfaces:** consome o CLI da Task 9.

- [ ] **Step 1:** Escrever os serviços `Type=oneshot`, `WorkingDirectory=%h/segundo-cerebro/00-Sistema/scripts`, `ExecStart=/usr/bin/python3 -m newsletter_ia coletar` (e `triar`), `TimeoutStartSec=300` para coletar e `3600` para triar. Timers: coletar `OnCalendar=*-*-* 04:30:00`, triar `OnCalendar=*-*-* 05:00:00`, `[Install] WantedBy=timers.target`, como `coletor.timer`. Horários são escolha do plano (madrugada, fora do uso).
- [ ] **Step 2:** `systemctl --user daemon-reload && systemd-analyze --user verify newsletter-ia-coletar.service newsletter-ia-triar.service` → sem erros.
- [ ] **Step 3:** `systemctl --user start newsletter-ia-coletar.service && journalctl --user -u newsletter-ia-coletar.service -n 20 --no-pager` → linhas `ok:` por fonte. **Não** rodar `enable` nem ligar o timer ainda (Task 12).

### Task 11: Skill `montar-edicao`

**Files:**
- Create: `~/.claude/skills/montar-edicao/SKILL.md`

- [ ] **Step 1:** Escrever a skill, disparada por "monta a edição". Conteúdo fixo, tirado do Design: (1) rodar `cd ~/segundo-cerebro/00-Sistema/scripts && python3 -m newsletter_ia candidatos`; (2) escolher ~10 itens: cerca de 5–6 `tecnica`, 2 `mercado`, 1–2 `repositorio`, 1 `decisao-projeto` (orientação, não cota); (3) **abrir uma amostra dos links** (ao menos 3) e conferir que o `motivo` do `agy` bate com a fonte, descartando item que não bata; (4) cada item com título, link, data e uma linha "por que importa para você"; itens com `marketing: true` levam a marca "(blog do próprio lab)"; (5) criar **rascunho** no Gmail para `destinatario` do `~/.config/newsletter-ia/config.json` (HTML se o conector aceitar, senão texto simples com links); (6) rodar `python3 -m newsletter_ia rascunhado ID...`; (7) só quando Guilherme disser que enviou, rodar `publicado ID...`; se descartar, `reverter ID...`; (8) perguntar quais itens ele leu e achou úteis e rodar `util ID sim|nao`. Proibido: enviar e-mail, escrever a destinatário diferente do configurado, incluir item sem link e data.
- [ ] **Step 2 (verificação real):** criar `~/.config/newsletter-ia/config.json` com o destinatário; numa sessão do Claude, criar um rascunho de teste com 2 itens fictícios e confirmar no Gmail que o rascunho existe, vai para o destinatário certo e mostra se HTML foi aceito. Registrar o resultado (HTML sim/não) no Design.

### Task 12: Gate de validação e ligar os timers

**Files:** nenhum arquivo de código.

- [ ] **Step 1:** Garantir ≥ 150 itens `coletado` (rodar `coletar`; se faltar volume, esperar dois dias de coleta) e rodar `python3 -m newsletter_ia triar` manualmente.
- [ ] **Step 2:** `python3 -m newsletter_ia amostra` → 20 itens. Numa sessão do Claude, Guilherme classifica cada um como bom/ruim em caixas de seleção; o Claude grava `rotulos.json` (`{"<id>": "bom"|"ruim"}`) em `/tmp`.
- [ ] **Step 3:** `python3 -m newsletter_ia concordancia /tmp/rotulos.json`. **Se `PASSOU` (≥ 0,70)**: `systemctl --user enable --now newsletter-ia-coletar.timer newsletter-ia-triar.timer` e conferir `systemctl --user list-timers --no-pager | grep newsletter`. **Se `NAO PASSOU`**: não ligar; ajustar o prompt de `montar_prompt` com base nos itens em que o `agy` discordou e repetir os passos 2–3 com uma nova amostra.
- [ ] **Step 4:** Registrar no Design (seção "Como saber se está bom") a data e a concordância medida.

---

## Auto-revisão
- **Cobertura do Design:** metas 1–5 → Tasks 3–5 (coleta), 2 (banco/dedupe), 6 (triagem), 7 e 11 (edição e rascunho). Anti-metas: item sem fonte → Task 11 passo 1 e 3; envio a terceiros → Global Constraints e Task 11; repetição entre edições → estados da Task 7; dado privado ao `agy` → Global Constraints. Validação de 70% → Tasks 8 e 12. Decisões da revisão (estados reversíveis, janela de 14 dias, teto de 150, carga de 7 dias, pré-filtros, `fonte_tipo=lab`) → Tasks 2–7.
- **Desvio do Design:** Anthropic Engineering e release notes só entram se tiverem feed (Task 5, passo 1); o Design os lista como "lidos direto", mas raspar HTML foi deixado fora da v1 por fragilidade.
- **Âncoras de calibração:** o Design pedia "dois itens-âncora de nota conhecida em cada lote"; o plano os implementa como dois exemplos fixos dentro do prompt (Task 6), não como itens reais no lote.
- **Consistência de tipos:** `Item`, `Triagem`, `coletar(...)`, `candidatos(...)` e os verbos do CLI usam os mesmos nomes entre tasks.
