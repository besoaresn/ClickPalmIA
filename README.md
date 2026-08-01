# Extrator Agêntico de Exames (browser-use + LLM + LangGraph)

Extrai laudos de mama do portal HMV e salva os PDFs localmente. Diferente de
um RPA determinístico, aqui um **agente de IA dirige o browser** de ponta a ponta
(navega, busca, abre exames), mas delega a parte que precisa ser **confiável** —
capturar o PDF do laudo — para uma **tool determinística** portada do RPA maduro.
Resultado: a adaptabilidade da IA + a robustez do código testado.

## Arquitetura

```
LangGraph (state machine)
  load_queue ──> open_browser ──> process ──(loop por paciente)──> finalize
                                     │
                                     └─ Agent (browser-use + LLM)
                                          • navega/clica/busca  (ações nativas)
                                          • download_exam_report (tool nossa, via CDP)
                                              ├─ FETCH    : baixa o PDF do iframe/blob
                                              │             (cookies de sessão inclusos)
                                              └─ HTML->PDF: fallback Page.printToPDF
                                          • saída estruturada (Pydantic SaidaAgente)
```

- **O agente decide**; as **tools executam** o trabalho frágil de forma determinística.
- **Sem** injeção de JS via prompt e **sem** watchdog varrendo `%TEMP%` (a versão antiga).
- **Sem** parsing por regex: o agente devolve `SaidaAgente` (Pydantic) via `output_model_schema`.

## Documentação

- [Fluxo do agente](docs/fluxo-agente.md): passo a passo técnico da execução,
  da fila da planilha ao download local, relatórios e retomada.
- [Quadro visual do fluxo](docs/fluxo-agente-board.svg): versão desenhada em
  formato SVG, pronta para abrir no navegador ou importar em ferramentas como Miro.


## Estrutura

| Caminho | Papel |
|---|---|
| `app/main.py` | Entrypoint: monta e roda o grafo |
| `app/pipeline/graph.py` | LangGraph: fila → browser → loop por paciente → relatório |
| `app/agent/runner.py` | Monta o `Agent` (Gemini ou AWS Bedrock + tools) por paciente |
| `app/agent/tools.py` | `download_exam_report` — tool determinística (CDP) |
| `app/agent/extraction.py` | Estratégias de PDF via CDP (FETCH, HTML→PDF) |
| `app/agent/prompts.py` | Prompt da tarefa do agente |
| `app/domain/filters.py` | Filtros puros de exame (data/keyword/skip) — unit-testados |
| `app/domain/history.py` | Histórico anti-duplicação + normalização de nomes |
| `app/domain/models.py` | Schemas Pydantic |
| `app/integrations/sheets.py` | Fila do Google Sheets (STATUS=1) + update de status |
| `app/reporting/manager.py` | `ReportManager` (relatórios de execução e de erros) |
| `app/core/config.py` | Env, seletores, keywords, timeouts |
| `app/core/runstate.py` | Estado compartilhado entre grafo e tool durante um paciente |

Os pacotes `integrations`, `reporting`, `domain` e `core` concentram as partes
portadas quase 1:1 do projeto `RPA_com_Agente_IA`.

## Configuração

```bash
pip install -r requirements.txt
playwright install chromium   # browser-use usa o Chromium do Playwright
```

Crie na raiz:
- **`credenciais.json`** — conta de serviço Google (Editor na planilha).
- **`.env`** — baseado em `.env.example`:

```env
PORTAL_USER=...            # login do portal HMV (usado pelo agente)
PORTAL_PASS=...
LLM_PROVIDER=gemini        # gemini ou bedrock
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_FALLBACK_API_KEY=... # chave de outro projeto Google
GEMINI_FALLBACK_MODEL=gemini-3.1-flash-lite
SHEET_URL=https://docs.google.com/spreadsheets/d/SEU_ID/edit
HEADLESS=false            # true = sem janela
```

O fallback do Gemini troca para `GEMINI_FALLBACK_API_KEY` quando a primeira
chave retornar quota/limite (`429`, `RESOURCE_EXHAUSTED` etc.) e mantém a
segunda chave ativa para os próximos pacientes do mesmo lote. As duas chaves
devem estar em projetos Google diferentes para que as quotas sejam independentes.
O preço padrão registrado nas métricas é US$ 0,25 por milhão de tokens de
entrada e US$ 1,50 por milhão de tokens de saída do Gemini 3.1 Flash-Lite.

Para publicar os resultados das métricas sem expor PDFs de pacientes, configure
na task definition:

```env
RESULTS_S3_URI=s3://clickpalmia-metricas-857145323577/apa
```

Ao final da execução, o aplicativo envia somente `telemetria/` e `reports/`
para esse prefixo. PDFs permanecem no EFS/disco local. A Task Role precisa de
`s3:PutObject`, `s3:GetObject` e `s3:ListBucket` no bucket privado.

`STORAGE_BACKEND=s3`/`S3_BUCKET` continua disponível para o armazenamento legado
de artefatos, mas não deve ser usado para o fluxo de métricas quando
`RESULTS_S3_URI` estiver configurado.

Para usar Claude via AWS Bedrock, troque o bloco de LLM:

```env
LLM_PROVIDER=bedrock
BEDROCK_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_FALLBACK_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_MAX_TOKENS=8192
BEDROCK_RETRY_ATTEMPTS=3
BEDROCK_AUTH_MODE=default
AWS_REGION=us-east-1
BEDROCK_API_KEY=          # opcional: API key do Bedrock
AWS_BEARER_TOKEN_BEDROCK= # opcional: mesmo valor, nome oficial AWS
AWS_ACCESS_KEY_ID=        # opcional: par IAM/STS
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=        # preencher só se a credencial IAM/STS for temporária
```

O prefixo `us.` é o inference profile exigido pela AWS para invocar o Claude
Haiku 4.5 (e demais modelos Claude recentes) nas regiões dos EUA, como
`us-east-1` — o modelo não aceita invocação direta on-demand sem esse profile.
Custo: ~$1,10/milhão de tokens de entrada e ~$5,50/milhão de saída (rate card
AWS Bedrock, `us-east-1`). Ver `docs/bedrock-deploy/` para os scripts de deploy
e o passo a passo de liberação de acesso ao Bedrock numa conta nova.
Com `BEDROCK_AUTH_MODE=default`, o boto3 pode usar chaves no `.env`, perfil/SSO
da AWS, role da máquina ou token/API key suportado pela configuração AWS local.
Não coloque a API key do Bedrock em `AWS_ACCESS_KEY_ID`; ela deve ir em
`AWS_BEARER_TOKEN_BEDROCK` ou `BEDROCK_API_KEY`.

## Executar

```bash
python -m app.main
```

Lê a planilha (pacientes com `STATUS=1`), processa cada um com o agente e, ao final,
gera `data/reports/execucao_*.txt` e `data/reports/erros_*.json`. PDFs ficam em
`data/downloads/`. Paciente concluído tem `STATUS` zerado na planilha — re-rodar
retoma de onde parou.

## Métricas

A execução também grava telemetria bruta em `data/metricas/telemetria/run_*.json`.
Para gerar os CSVs usados no artigo:

```bash
python calcular_metricas.py --gerar-gabarito
# revise data/metricas/gabarito.csv, coluna autorizado (1/0)
python calcular_metricas.py --validar-gabarito
python calcular_metricas.py
```

O refinador gera `data/metricas/refinado/geral.csv` e
`data/metricas/refinado/detalhado_<run_id>.csv` com Bloco 1
(VP/FP/FN/VN, acurácia, precisão, revocação e F1) e Bloco 3
(login, busca, download unitário e download completo), usando a janela
2024-2025.

## Testes

```bash
pytest tests/        # filtros puros (janela 2024-2025, keywords de mama, skip de carta)
```

Smoke ao vivo: rode com `HEADLESS=false` e 1 paciente conhecido na planilha; observe
login → busca → abertura do laudo → `download_exam_report` salvando um PDF válido
(`%PDF`) em `data/downloads/`.
