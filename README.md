# newsletter-ia

Newsletter pessoal de IA montada direto das fontes de origem (labs, arXiv, GitHub, Hacker News, Hugging Face), sem passar por Instagram nem agregadores.

Um timer coleta e guarda tudo num SQLite. Outro manda o `agy` (Antigravity CLI, cota do Google) dar nota e etiqueta a cada item. Na hora de ler, o Claude escolhe ~10 itens, confere os links e adiciona a edição da semana a uma **página HTML local**, uma seção por semana. Nada sai da máquina.

> Projeto privado, feito para uso próprio numa máquina Linux sempre ligada. Não é um pacote para terceiros.

## Como funciona

```
04:30  coletar   APIs e feeds ──► SQLite (~/.local/state/newsletter-ia/itens.db)   estado: coletado
05:00  triar     lotes de 15 ──► agy -p --mode plan --json-schema ──► nota/etiqueta  estado: triado
sob    "monta a  Claude (skill montar-edicao) ──► candidatos ──► edicoes/semana-N.json
demanda edição"  python3 -m newsletter_ia edicao ──► index.html (abre no navegador)  estado: publicado
```

| Etapa | Quem faz | Custo |
|---|---|---|
| Coleta e deduplicação | código Python (sem LLM) | zero |
| Triagem em volume | `agy` | ~50 a 95 mil tokens de entrada por lote, até 10 lotes/dia |
| Curadoria e escrita | Claude, pela skill | uma sessão por semana |

## Fontes (v1)

| Fonte | Como | Filtro |
|---|---|---|
| arXiv `cs.LG`, `cs.CL`, `cs.MA`, `cs.AI` | API Atom, 300 por categoria, 3 s entre chamadas | termo de IA no título **ou** paper presente no HF Daily Papers |
| Hugging Face Daily Papers | `api/daily_papers?sort=trending` | — |
| Hacker News | Algolia `search_by_date` | ≥ 50 pontos |
| GitHub | `search/repositories` (não existe API de trending) | criado no período, push nos últimos 30 dias, descarta salto de > 20 mil estrelas em < 7 dias |
| Feeds | DeepMind, HF blog, Microsoft Research, OpenAI, Interconnects, Import AI, Latent Space | — |

Anthropic não tem feed (404) e fica fora da v1.

## Requisitos

- Linux com systemd de usuário e Python 3.12 (`/usr/bin/python3`)
- `requests` (`pip install -r requirements.txt`; já vem no Python do sistema da máquina atual)
- `agy` no `PATH`, logado
- Claude Code, para a etapa de curadoria

## Instalação

```bash
git clone https://github.com/Guilherme-L-C/newsletter-ia.git ~/newsletter-ia
cd ~/newsletter-ia
python3 -m unittest tests.test_newsletter_ia        # 66 testes, sem rede

# timers
ln -sf ~/newsletter-ia/systemd/newsletter-ia-* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now newsletter-ia-coletar.timer newsletter-ia-triar.timer

# skill do Claude
ln -sfn ~/newsletter-ia/skill/montar-edicao ~/.claude/skills/montar-edicao
```

Antes de ligar os timers numa instalação nova, faça a validação inicial (ver [Validar a triagem](#validar-a-triagem)).

## Uso

Todos os comandos rodam a partir da raiz do repo: `python3 -m newsletter_ia <comando>`.

| Comando | O que faz |
|---|---|
| `coletar` | Busca o que é novo em cada fonte (com 4 dias de margem) e grava. Sai com 1 se alguma fonte falhar; as outras seguem. |
| `triar` | Manda até 150 itens/dia ao `agy`, em lotes de 15. Sai com 1 se o `agy` quebrar. |
| `candidatos` | JSON com até 25 itens triados dos últimos 14 dias, no máximo 8 por fonte. |
| `edicao ARQ.json` | Grava a edição da semana em `edicoes/semana-NNN.json` e regenera o `index.html`. Mesmo número substitui. |
| `publicado ID...` | Marca os itens que entraram na edição (não voltam aos candidatos). |
| `rascunhado ID...` / `reverter ID...` | Estado intermediário, para separar e devolver itens antes de publicar. |
| `util ID sim\|nao` | Registra se o item foi útil. |
| `amostra` | 20 itens espalhados pela faixa de notas, para validação. |
| `concordancia ARQ.json` | Compara rótulos `{"id": "bom"\|"ruim"}` com a nota do `agy`; imprime `PASSOU` se ≥ 0,70. |

Para a edição da semana, numa sessão do Claude Code: **"monta a edição"**. A skill [`montar-edicao`](skill/montar-edicao/SKILL.md) roda `candidatos`, escolhe, confere links, escreve a edição, regenera a página e abre no navegador.

A página fica em `~/segundo-cerebro/01-Projetos/newsletter-ia/index.html` (na vault, sincroniza com o Mac). Cada semana tem número, tema e as seções da edição; a mais recente fica no topo.

### Operação

```bash
systemctl --user list-timers | grep newsletter
journalctl --user -u newsletter-ia-coletar.service -n 30 --no-pager
journalctl --user -u newsletter-ia-triar.service -n 30 --no-pager
sqlite3 ~/.local/state/newsletter-ia/itens.db "select estado, count(*) from itens group by estado"
```

### Validar a triagem

```bash
python3 -m newsletter_ia triar
python3 -m newsletter_ia amostra > /tmp/amostra.json
# classifique cada id como "bom" ou "ruim" em /tmp/rotulos.json
python3 -m newsletter_ia concordancia /tmp/rotulos.json
```

## Configuração

Constantes em [`newsletter_ia/config.py`](newsletter_ia/config.py):

| Constante | Valor | Para quê |
|---|---|---|
| `TETO_AGY_DIA` | 150 | itens enviados ao `agy` por dia |
| `LOTE_AGY` | 15 | itens por chamada (~73 s) |
| `CARGA_INICIAL_DIAS` | 7 | janela da primeira coleta |
| `MARGEM_DIAS` | 4 | sobreposição entre coletas (fontes publicam com atraso) |
| `JANELA_DIAS` | 14 | idade máxima de um candidato |
| `MAX_POR_FONTE` / `N_CANDIDATOS` | 8 / 25 | limites da lista de candidatos |
| `HN_PONTOS_MIN` | 50 | corte do Hacker News |
| `NOTA_CORTE_BOM` / `CONCORDANCIA_MIN` | 6 / 0,70 | validação |

Etiquetas do `agy`: `tecnica` (peso maior), `mercado`, `repositorio`, `decisao-projeto`, `descartar`.

## Estrutura

```
newsletter_ia/       pacote (CLI em __main__.py)
  fontes/            uma fonte por arquivo
  coletar.py         orquestra fontes, isola falhas
  triar.py           prompt, chamada ao agy, validação da resposta
  selecao.py         candidatos e estados
  validacao.py       amostra e concordância
  pagina.py          página HTML com todas as edições
tests/               unittest, sem rede
systemd/             units de coleta e triagem
skill/montar-edicao/ skill do Claude Code
docs/                design (por quê, decisões) e plano de implementação
```

## Limitações conhecidas

- A validação inicial (0,75) teve pouco poder: 18 de 20 itens foram marcados "bom". O `agy` é mais rígido que o leitor.
- Pendências menores registradas na revisão final: feed com data `-0000` derruba aquele feed; datas de RSS não são convertidas para UTC; o teto diário conta itens triados com sucesso, não enviados; títulos não têm quebras de linha removidas antes do prompt; acentos podem corromper em feed sem charset; `TimeoutStartSec=300` da coleta abaixo do pior caso.
- A coleta do GitHub só vê repositórios criados no período; um repo antigo que explode depois não entra.
- O `agy` dá nota 9 a 10 a repositórios novos e pessoais com README caprichado (0 a 1 estrela). Hoje a skill confere e descarta na mão; falta um filtro de estrelas mínimas na coleta.

## Próximos passos

v2 em formato revista (seções Radar, Científica, Programação, IA, Ideias inovadoras, Analistas e Hardware, ~1 h de leitura). Detalhes em [`docs/design.md`](docs/design.md#v2--formato-revista-definido-com-o-guilherme-em-2026-10-24-ainda-sem-plano-de-execução).

## Licença

Privado, sem licença de uso. Todos os direitos reservados.
