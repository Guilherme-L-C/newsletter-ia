---
title: Newsletter IA — Design
type: projeto
tags: [ia, newsletter, agy, design, automacao]
status: design
updated: 2026-10-24
---

> **Nota (2026-10-24):** cópia da nota do mesmo nome na vault (`segundo-cerebro/01-Projetos/`). O código saiu de `00-Sistema/scripts/newsletter_ia/` e agora mora **neste repositório** (`~/newsletter-ia`). Caminhos antigos abaixo valem como histórico.

# Newsletter IA — Design

## Intenção (o porquê)
Guilherme acompanha IA (técnicas, mercado, repositórios, o que construir) quase só por Instagram, onde chega de segunda mão, misturado com venda. Quer ir direto às fontes de origem (labs, arXiv, GitHub, HN, Hugging Face) sem gastar horas caçando.

Objetivo: **uma edição semanal de ~10 itens, escolhidos de dentro de um volume grande, entregue por e-mail no Gmail**, com link e data em cada item e uma linha dizendo por que importa.

O trabalho pesado (ler e filtrar em volume) vai para o `agy` (cota do Google). O Claude entra só no julgamento final e na escrita.

## Metas
1. Coleta automática diária, por API pública, de arXiv, GitHub, Hacker News e Hugging Face Daily Papers, mais os feeds/changelogs dos labs (lista em "Fontes iniciais").
2. Banco local com tudo que foi visto, sem repetir item entre edições.
3. Triagem automática pelo `agy`: cada item novo recebe nota de relevância e uma etiqueta do motivo (ver "Etiquetas").
4. Edição semanal de ~10 itens, **peso maior em "aprender técnicas"**, com poucos itens de mercado, repositório e decisão de projeto.
5. A edição chega como **rascunho no Gmail**, e Guilherme revisa/envia para si mesmo.

## Não-metas
- Sem site, sem assinantes, sem envio para mais ninguém.
- Sem chave de API paga nova. Só APIs públicas sem chave e a cota do `agy`.
- Sem tentar cobrir "tudo": poucas fontes, boas e ativas.
- Sem YouTube e Reddit na primeira versão (TubeAlfred sem créditos; Reddit bloqueou a leitura).
- Sem automatizar o passo de curadoria final nesta fase (ver Abordagens).

## Anti-metas (falha mesmo se "funcionar")
- **Item inventado ou sem fonte.** Todo item da edição tem link e data lidos de verdade. Sem link, não entra.
- **Enviar e-mail para outra pessoa.** Só o próprio Guilherme recebe (mesma regra do Assistente Telegram).
- **Virar outra enxurrada.** Mais de ~10 itens, ou itens que ele nunca lê, é falha.
- Repetir o mesmo item em edições diferentes.
- Marketing do lab apresentado como tendência independente sem aviso.
- Mandar ao `agy` qualquer dado pessoal ou privado. Só conteúdo público.

## Restrições
- Roda no PC Linux (`guilherme-desktop`, ligado quase sempre), como serviço/timer systemd, igual ao Radicale e ao relay do Telegram.
- Python, como os scripts de `00-Sistema/scripts/`. Código novo em `00-Sistema/scripts/newsletter_ia/`.
- `agy -p` leva de 30 s a ~4 min por resposta. Por isso a triagem roda em lotes e fora do horário de uso, nunca com a pessoa esperando.
- O MCP Google existente (`google_workspace_mcp.py`) é só leitura. **Não** serve para enviar e-mail. O rascunho no Gmail é criado pelo Claude, com o conector de Gmail da sessão.
- Limites das APIs (verificados em 2026-10-24):
  - arXiv: usar `https://export.arxiv.org/api/query`; 3 s entre chamadas; cache; resposta em XML (Atom).
  - GitHub: `GET /search/repositories`; 10 req/min sem login, 30 com; máx. 1.000 resultados; **não há endpoint oficial de trending** (aproximar por `created:>data` + `sort=stars`).
  - Hacker News: Firebase sem limite documentado; Algolia (`hn.algolia.com/api/v1/search_by_date`) respondeu sem chave, termos não lidos.
  - Hugging Face: `GET huggingface.co/api/daily_papers` respondeu 200 sem token; parâmetros `date`/`week` só vistos em fontes de terceiros.
- Fontes que bloquearam leitura automática: OpenAI News (HTML), Arena, Reddit. O RSS da OpenAI funcionou.

## Abordagens consideradas
- **A. Tudo automático na máquina** (cron coleta, `agy` tria, `claude -p` escreve, envia e-mail). Zero esforço semanal, mas mais peças frágeis (e-mail sem sessão, Claude headless) e a qualidade só aparece depois de enviada.
- **B. Triagem automática, curadoria com o Claude (escolhida por Guilherme).** Coleta e `agy` rodam sozinhos. Na segunda Guilherme abre uma sessão e pede "monta a edição"; o Claude lê só os candidatos já triados, escolhe, escreve e cria o rascunho no Gmail. Custo: ~2 min manuais por semana. Ganho: a parte cara é automática e o julgamento fica sob o olho dele até o critério provar que funciona.
- **C. Tudo na nuvem, sem `agy`.** Roda sem a máquina, mas gasta só o plano do Claude e não alcança o `agy`. Descartada.

Evolução prevista: B → A, trocando o passo manual por um agendamento. Nada é refeito.

## Desenho (abordagem B)

### Fluxo
1. **Timer diário** roda `coletar`: busca em cada fonte só o que é novo desde a última execução e grava no SQLite.
2. **Timer diário** (depois da coleta) roda `triar`: pega itens ainda sem nota, manda em lotes ao `agy -p`, grava nota e etiqueta.
3. **Sob demanda** (Guilherme diz "monta a edição"): o Claude roda `candidatos`, que imprime em JSON compacto os ~25 itens com maior nota ainda não publicados. O Claude escolhe ~10, escreve, cria o rascunho no Gmail e roda `marcar-publicados` com os IDs escolhidos.

### Banco (SQLite, um arquivo)
Tabela `itens`: `id` (hash da URL), `fonte`, `titulo`, `url`, `data_publicacao`, `data_coleta`, `resumo_bruto`, `nota` (0–10, nula até triar), `etiqueta`, `motivo` (1–2 linhas), `publicado_em` (nulo até entrar numa edição).
Deduplicação por `id`. Itens nunca são apagados, só marcados.

### Etiquetas (saída do `agy`)
`tecnica` · `mercado` · `repositorio` · `decisao-projeto` · `descartar`.
O `agy` devolve JSON com schema fixo (`--output-format json` e `--json-schema`): `id`, `nota`, `etiqueta`, `motivo`. Modo `plan`, sem acesso a escrita. A nota já embute a prioridade de Guilherme: `tecnica` pontua mais alto, a menos que o item seja claramente excepcional em outra etiqueta.

### Regras de seleção (para o Claude)
- ~10 itens: cerca de 5 a 6 `tecnica`, 2 `mercado`, 1 a 2 `repositorio`, 1 `decisao-projeto`. É orientação, não cota rígida.
- Cada item: título, link, data, uma linha "por que importa para você".
- Itens vindos do blog do próprio lab que são marketing levam marcação.
- **Antes de escrever, o Claude abre uma amostra dos links** para conferir que o resumo do `agy` bate com a fonte.

### Fontes iniciais
- arXiv: `cs.LG`, `cs.CL`, `cs.MA` (e `cs.AI`), ordenado por data.
- Hugging Face Daily Papers (`sort=trending`).
- Hacker News (Algolia, busca por termos de IA e `points` mínimos).
- GitHub (busca por tópicos de IA criados na última semana, ordenados por estrelas, filtrando por atividade).
- Feeds RSS confirmados: DeepMind, Hugging Face blog, Microsoft Research, OpenAI.
- Páginas sem RSS lidas direto: Anthropic Engineering, release notes da Anthropic.
- Newsletters: Interconnects, Import AI, Latent Space (conferir se têm RSS).

## Decisões do Guilherme
- Critério de importância: aprender técnicas, ficar no mercado, achar repositórios e decidir o que construir, **com peso maior em aprender técnicas**.
- Edição semanal de ~10 itens.
- Entrega por e-mail no Gmail.
- Máquina quase sempre ligada → pode rodar tudo local.
- Abordagem B.

## Decisões minhas (podem ser vetadas)
- SQLite em vez de outro banco.
- Coleta e triagem diárias, edição semanal.
- Systemd timer, não cron, seguindo o padrão da máquina.
- Código em `00-Sistema/scripts/newsletter_ia/`, em Python.
- Rascunho no Gmail criado pelo Claude (e não envio pelo script), porque o MCP Google é só leitura e a regra é só enviar a si mesmo.
- Etiquetas e faixa de itens por etiqueta acima.

## Decisões minhas após a revisão (podem ser vetadas)
- **Gatilho da edição:** uma skill do Claude, `montar-edicao`, disparada pela frase "monta a edição". Roda a partir de `00-Sistema/scripts/newsletter_ia/` e chama `candidatos`. A skill guarda as regras de seleção deste documento.
- **Estados do item:** `coletado` → `triado` → `rascunhado` → `publicado`. `marcar-publicados` só roda quando Guilherme confirma que enviou o e-mail. Rascunho descartado volta os itens para `triado`. A operação é reversível.
- **Feedback de leitura:** coluna `util` (sim/não/nulo). O Claude preenche quando Guilherme diz, na sessão, o que leu e achou útil. Sem formulário novo.
- **Destinatário:** o próprio Guilherme. O endereço fica num arquivo de configuração local, fora deste documento. Se o conector Gmail não aceitar HTML, a edição vai em texto simples com links, sem plano B mais complexo.
- **Janela de candidatos:** itens dos últimos 14 dias. `descartar` nunca entra. No máximo 8 candidatos por fonte, para o top 25 não vir de uma só.
- **Nota entre lotes:** o `agy` recebe sempre o mesmo prompt e dois itens-âncora de nota conhecida em cada lote, para calibrar. O Claude trata a nota como ordenação, não como medida absoluta.
- **Primeira carga:** só os últimos 7 dias. Teto de 150 itens por dia enviados ao `agy`. O excedente é adiado para o dia seguinte, não descartado.
- **Pré-filtro antes do `agy`:** arXiv só entra se tiver termo de IA no título ou aparecer no HF Daily Papers. HN só acima de um mínimo de pontos. GitHub só com commit nos últimos 30 dias e sem repositório recém-criado com salto absurdo de estrelas.
- **Aviso de marketing:** campo `fonte_tipo = lab` na tabela. Todo item vindo de blog de lab recebe a marcação. O `agy` não decide isso.
- **Validação inicial:** o Claude mostra ~20 itens reais numa sessão, Guilherme classifica em caixas de seleção (bom/ruim), e a concordância com a nota do `agy` precisa chegar a **70%** antes de ligar o timer. O limiar de 70% é palpite meu, ajustável.
- **Lembrete de 8 dias:** fora da primeira versão.

## O que fica para quem construir
- ~~Confirmar que `agy -p --output-format json --json-schema ...` funciona~~ **Feito em 2026-10-24 (Task 1 do plano):** `--json-schema` funciona com `--mode plan`, mas a **raiz do schema precisa ser `object`** (array na raiz dá erro). Usar `{"itens":[...]}`; a resposta vem em `response` (texto JSON) e também em `structured_output`. Lote de 15 itens: **73 s**, notas coerentes. Latência de chamada mínima: 20 a 45 s. Cada chamada consome ~50 a 95 mil tokens de entrada (prompt de sistema do `agy`), então a cota diária pesa: 150 itens = 10 chamadas. `LOTE_AGY` fica em 15.
- Formato exato do e-mail (HTML simples ou texto).
- Tratamento de falha por fonte: uma fonte fora do ar não pode derrubar a coleta.
- Descobrir se o conector Gmail do Claude permite criar rascunho com HTML.
- Conferir termos da API Algolia do HN e os parâmetros do `daily_papers` na especificação OpenAPI oficial da Hugging Face.
- Investigar o repositório anômalo visto no GitHub (`morluto/rea`, ~88 mil estrelas em uma semana) antes de usar GitHub como sinal: filtrar por atividade real.

## Como saber se está bom
- **Antes de ligar o timer:** Guilherme classifica ~20 itens reais como "bom" ou "ruim". Testa-se a triagem do `agy` contra isso. Se a concordância for baixa, ajusta-se o prompt antes de seguir.
- **Depois:** em cada edição, Guilherme marca quais itens leu e achou úteis. Essa taxa orienta o critério.
- **Custo e falha:** cada execução registra quantos itens coletou, triou e falhou.

## Riscos
- Resumo do `agy` impreciso → mitigado pela amostragem e pela regra de link/data obrigatórios.
- Cota gratuita do `agy` estourar → lotes pequenos e limite diário.
- Fontes mudarem de formato ou bloquearem → falha isolada por fonte e aviso no log.
- Passo manual semanal ser esquecido → na primeira versão não há lembrete automático; é decisão registrada acima.

## Desvios registrados na execução (2026-10-24)
- **Anthropic Engineering e News fora da v1:** não têm feed (404 em `/engineering/rss.xml`, `/news/rss.xml`, `/rss.xml`). Raspar HTML ficou para uma v2.
- **Feeds ativos na v1:** DeepMind, Hugging Face blog, Microsoft Research, OpenAI, Interconnects, Import AI e Latent Space (todos responderam 200 com `requests`; Microsoft devolveu 403 ao `curl` por causa do User-Agent).
- **Conector Gmail (testado em 2026-10-24):** `create_draft` aceita `htmlBody` e `to`; o rascunho foi criado para o próprio Guilherme e lido de volta com HTML intacto. O Gmail reescreve os links como redirecionamentos `google.com/url?q=...` (comportamento normal). O rascunho de teste foi apagado.
- **GitHub no uso diário:** `created:>=<data>` filtra por dia de criação, então a coleta diária só vê repositórios criados desde a última coleta; um repositório antigo que explode em estrelas depois não entra. Aceito na v1.

## Ideias para depois (não fazem parte da v1)
- **Formato revista, por seções (ideia do Guilherme, 2026-10-24):** em vez de uma lista única de ~10 itens, a edição seria organizada como uma revista, com seções fixas (por exemplo técnicas, mercado, repositórios, o que construir). Hoje as etiquetas do `agy` (`tecnica`, `mercado`, `repositorio`, `decisao-projeto`) já separam o conteúdo nessas gavetas, então a mudança seria sobretudo de apresentação na skill `montar-edicao`. Pontos a decidir quando for a hora: número de itens por seção, se há seção fixa mesmo em semana fraca, e se vale um tom de editorial curto no início de cada seção.
- **Seções propostas para a revista (ideia do Guilherme, 2026-10-24):** Científica, Mercado, Ideias inovadoras, IA, Programação e Analistas. Hoje as etiquetas do `agy` são `tecnica`, `mercado`, `repositorio`, `decisao-projeto` e `descartar`; as seções novas pediriam um conjunto de etiquetas diferente e, para "Analistas" e "Ideias inovadoras", fontes que a v1 ainda não coleta (relatórios e análises de mercado, tendências de produto). Fica como etapa futura: redefinir etiquetas e fontes antes de mexer na apresentação.
- **Ilustrações geradas por IA (ideia do Guilherme, 2026-10-24):** integrar um agente gerador de imagem para ilustrar itens ou seções da revista. Sem escolha de ferramenta ainda. Pontos a decidir: quais itens ganham imagem (capa e abertura de seção, não todos), custo/cota da geração, e se a imagem entra no e-mail em HTML (o conector de Gmail aceita anexo inline, mas isso não foi testado).

## Validação inicial (2026-10-24)
- Amostra de 20 itens reais triados pelo `agy`, embaralhada e sem a nota à vista; Guilherme classificou como bom/ruim. Resultado: **18 bons e 2 ruins**; concordância com o `agy` = **0,75** (limiar 0,70) → timers ligados (`newsletter-ia-coletar` 04:30, `newsletter-ia-triar` 05:00).
- **Limite do teste:** como quase tudo foi marcado "bom", o teste tem pouco poder de detectar um `agy` frouxo. O que ele mostrou: o `agy` é **mais rígido** que o Guilherme (4 dos 5 desacordos são itens que o `agy` rebaixou e Guilherme acha bons: um utilitário de SQLite, um protótipo multiagente genérico, um repositório vazio e o mapeamento de florestas da DeepMind). Um desacordo foi o contrário (`thoughtspace`).
- Para ajustar: se faltar variedade nas edições, relaxar o prompt para repositórios e itens de IA aplicada; se sobrar ruído, manter. Reavaliar com a taxa `util` das primeiras edições.

## v2 — Formato revista (definido com o Guilherme em 2026-10-24; ainda sem plano de execução)
**Por quê:** ele quer ler a edição por **mais de 1 hora por semana**, como uma revista, em vez de uma lista de ~10 itens.

**Estrutura (ordem de leitura):**
1. **Radar da semana** — ~8 linhas de notícia (lançamentos, preços, mudanças de API). Notícia envelhece em dias, então fica curta. Fontes: changelogs e blogs dos labs, já coletados.
2. **Científica** — papers e pesquisa (arXiv, Hugging Face Papers).
3. **Programação** — engenharia, técnicas, boas práticas e repositórios.
4. **IA** — modelos, agentes e ferramentas de IA.
5. **Ideias inovadoras** — tendências de produto e startups. **Fontes novas necessárias.**
6. **Analistas** — análise e opinião de especialistas. **Fontes novas necessárias.**
6b. **Hardware** — processadores, GPUs, aceleradores e chips para IA (ideia do Guilherme, 2026-10-24). **Fontes novas necessárias** (blogs de fabricantes, análises técnicas de hardware).
7. **Duas leituras longas** destacadas, para ler com calma.

Mercado **não** vira seção própria: fica dentro do Radar. Ilustrações geradas por IA continuam como ideia futura.

**Tamanho:** ~30 itens por edição (Radar de 8 linhas + ~5 itens por seção + 2 leituras longas), cerca de 1 hora de leitura.

**O que isso muda no código:**
- Etiquetas do `agy`: passam a seguir as seções (`noticia`, `cientifica`, `programacao`, `ia`, `ideias`, `analistas`, `hardware`, `descartar`), com a nota de relevância mantida. Peso maior continua em aprender técnicas.
- `N_CANDIDATOS` sobe de 25 para ~70; `MAX_POR_FONTE` precisa ser reavaliado.
- Skill `montar-edicao` monta por seção, com editorial curto por seção (a decidir).
- Coleta: **segunda rodada de pesquisa de fontes** para Ideias inovadoras, Analistas e Hardware, antes de mexer no código.

**Ordem sugerida:** (1) pesquisar fontes para as duas seções novas; (2) atualizar este desenho; (3) plano de execução; (4) construir. A v1 (lista de ~10 itens) continua valendo e rodando até a v2 ficar pronta.

