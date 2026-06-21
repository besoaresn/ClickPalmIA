# Extrator Agêntico de Exames (browser-use + Gemini + LangGraph)

Extrai laudos de mama do portal HMV e envia para a API ClickPalm. Diferente de
um RPA determinístico, aqui um **agente de IA dirige o browser** de ponta a ponta
(navega, busca, abre exames), mas delega a parte que precisa ser **confiável** —
capturar o PDF do laudo e enviar à API — para uma **tool determinística** portada
do RPA maduro. Resultado: a adaptabilidade da IA + a robustez do código testado.

## Arquitetura

```
LangGraph (state machine)
  load_queue ──> open_browser ──> process ──(loop por paciente)──> finalize
                                     │
                                     └─ Agent (browser-use + Gemini)
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
  da fila da planilha ao download, upload, relatórios e retomada.
- [Quadro visual do fluxo](docs/fluxo-agente-board.svg): versão desenhada em
  formato SVG, pronta para abrir no navegador ou importar em ferramentas como Miro.


## Estrutura

| Caminho | Papel |
|---|---|
| `app/main.py` | Entrypoint: monta e roda o grafo |
| `app/pipeline/graph.py` | LangGraph: fila → browser → loop por paciente → relatório |
| `app/agent/runner.py` | Monta o `Agent` (Gemini + tools) por paciente |
| `app/agent/tools.py` | `download_exam_report` — tool determinística (CDP) |
| `app/agent/extraction.py` | Estratégias de PDF via CDP (FETCH, HTML→PDF) |
| `app/agent/prompts.py` | Prompt da tarefa do agente |
| `app/domain/filters.py` | Filtros puros de exame (data/keyword/skip) — unit-testados |
| `app/domain/history.py` | Histórico anti-duplicação + normalização de nomes |
| `app/domain/models.py` | Schemas Pydantic |
| `app/integrations/sheets.py` | Fila do Google Sheets (STATUS=1) + update de status |
| `app/integrations/clickpalm.py` | Token + upload para a API ClickPalm |
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
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
CLICKPALM_LOGIN_URL=...
CLICKPALM_UPLOAD_URL=...
CLICKPALM_CPF=...
CLICKPALM_PASS=...
SHEET_URL=https://docs.google.com/spreadsheets/d/SEU_ID/edit
HEADLESS=false            # true = sem janela
```

## Executar

```bash
python -m app.main
```

Lê a planilha (pacientes com `STATUS=1`), processa cada um com o agente e, ao final,
gera `data/reports/execucao_*.txt` e `data/reports/erros_*.json`. PDFs ficam em
`data/downloads/`. Paciente concluído tem `STATUS` zerado na planilha — re-rodar
retoma de onde parou.

## Testes

```bash
pytest tests/        # filtros puros (data 2024+, keywords de mama, skip de carta)
```

Smoke ao vivo: rode com `HEADLESS=false` e 1 paciente conhecido na planilha; observe
login → busca → abertura do laudo → `download_exam_report` salvando um PDF válido
(`%PDF`) em `data/downloads/` → upload 200/201.
