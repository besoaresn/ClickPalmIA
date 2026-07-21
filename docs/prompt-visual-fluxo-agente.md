# Prompt para gerar o fluxo visual do agente

Copie o bloco abaixo e cole no ChatGPT para pedir uma versao visual do fluxo do
processo. O texto ja esta organizado para gerar um fluxograma/infografico de
artigo, com raias, decisoes e saidas.

```text
Quero que voce transforme o processo abaixo em um fluxograma visual para um
artigo academico/TCC.

Objetivo da figura:
Representar como um agente de IA percorre o fluxo completo de extracao de
laudos medicos: leitura da fila na planilha, acesso ao portal HMV, busca do
paciente, selecao dos exames, captura local do PDF, atualizacao de status e
geracao de relatorios.

Estilo desejado:
- Visual limpo, tecnico e adequado para artigo academico.
- Use blocos retangulares para etapas de processo.
- Use losangos para decisoes.
- Use raias/swimlanes para separar responsabilidades.
- Use setas direcionais claras.
- Destaque que o agente LLM decide a navegacao, mas a tool deterministica
  executa as operacoes criticas de download local e contagem.
- Evite excesso de texto dentro dos blocos; use frases curtas.
- A figura deve ser compreensivel mesmo para quem nao conhece o codigo.

Raias sugeridas:
1. Entrada e Orquestracao
2. Agente IA / browser-use
3. Portal HMV
4. Tool deterministica download_exam_report
5. Persistencia local e planilha
6. Relatorios e Retomada

Contexto do sistema:
O sistema e um pipeline Python que combina LangGraph, browser-use, LLM, Google
Sheets e Portal HMV.

A arquitetura possui tres responsabilidades principais:
1. Orquestracao deterministica:
   - app/main.py inicia a execucao.
   - app/pipeline/graph.py define o grafo LangGraph.
   - O grafo controla o lote: carregar fila, abrir browser, processar paciente
     e finalizar.

2. Navegacao agentica:
   - app/agent/runner.py cria um agente browser-use.
   - O agente usa um LLM para navegar no portal HMV.
   - Ele faz login se necessario, busca o paciente, abre o prontuario/lista de
     exames e identifica quais exames devem ser processados.

3. Operacoes criticas deterministicas:
   - app/agent/tools.py implementa a tool download_exam_report.
   - A tool baixa o PDF do laudo, verifica duplicidade, identifica laudos que
     devem ser ignorados, detecta indisponibilidade, salva o arquivo localmente
     e atualiza as contagens do relatorio.
   - A tool e a fonte de verdade das contagens, nao a resposta textual do LLM.

Fluxo macro:
1. Inicio da execucao com python -m app.main.
2. Validacao de configuracoes minimas, como SHEET_URL, credenciais do portal,
   provedor LLM.
3. Criacao do Pipeline.
4. Compilacao do grafo LangGraph.
5. Leitura da fila no Google Sheets.
6. A planilha retorna apenas pacientes com STATUS = 1.
7. Se nao houver pacientes, o sistema finaliza e gera relatorios.
8. Se houver pacientes, o sistema abre uma sessao unica de browser.
9. Para cada paciente da fila, o pipeline chama run_patient.
10. O agente acessa o portal HMV.
11. O agente faz login apenas se ainda nao estiver autenticado.
12. O agente busca o paciente pelo nome completo; se nao encontrar, tenta pelo
    primeiro nome.
13. Se o paciente nao for encontrado:
    - registra paciente nao encontrado;
    - atualiza STATUS = 0 na planilha;
    - segue para o proximo paciente.
14. Se o paciente for encontrado:
    - le o ID numerico do paciente;
    - lista os exames;
    - seleciona os exames alvo.
15. Exames alvo sao exames a partir de 2024 e relacionados a mama, conforme
    palavras-chave como MAMA, MAMO, BREAST, AXILA, IMPLANT, NODULO,
    ECOGRAFIA e ULTRASSONOGRAFIA.
16. Para cada exame alvo:
    - o agente abre o exame;
    - clica em Imprimir;
    - abre o relatorio/laudo;
    - chama a tool download_exam_report.
17. A tool download_exam_report:
    - recebe nome do paciente, ID do paciente, nome do exame, data do exame e
      CPF quando disponivel;
    - cria uma chave unica de historico;
    - verifica se o exame ja foi processado nesta execucao;
    - verifica se o exame ja foi baixado em execucao anterior;
    - le o texto do laudo via CDP;
    - identifica cartas de procedimento que devem ser ignoradas;
    - identifica mensagens de laudo indisponivel;
    - tenta extrair o PDF.
18. A extracao do PDF ocorre com duas estrategias:
    - FETCH: captura o PDF do iframe/blob usando a sessao autenticada;
    - HTML->PDF: fallback que renderiza a pagina atual como PDF.
19. Se o PDF for extraido:
    - salva o arquivo localmente;
    - registra sucesso e grava o historico.
20. A tool retorna uma mensagem ao agente:
    - OK;
    - JA_BAIXADO;
    - JA_PROCESSADO;
    - IGNORADO;
    - INDISPONIVEL;
    - FALHA.
21. O agente considera o exame concluido apos qualquer retorno da tool e segue
    para o proximo exame alvo.
22. Quando todos os exames alvo forem tentados, o agente retorna uma saida
    estruturada chamada SaidaAgente, contendo:
    - id_paciente;
    - nao_encontrado;
    - exames_baixados;
    - exames_indisponiveis.
23. O pipeline avalia o resultado real registrado pela tool:
    - se nao houve falhas reais, atualiza STATUS = 0 na planilha;
    - se houve falha real, mantem STATUS = 1 para reprocessamento futuro.
24. O grafo verifica se ainda ha pacientes.
25. Se houver, repete o fluxo para o proximo paciente.
26. Se nao houver, finaliza:
    - fecha o browser;
    - gera relatorio final execucao_*.txt;
    - gera relatorio de erros erros_*.json.

Ponto central que deve aparecer na figura:
O agente LLM e responsavel pela navegacao flexivel no portal, mas nao e
responsavel direto por baixar arquivos. A etapa critica e delegada a uma tool
deterministica, chamada download_exam_report, que garante mais controle,
rastreabilidade e confiabilidade.

Fluxograma base em Mermaid, se quiser usar como referencia:

flowchart TD
    A[Inicio: python -m app.main] --> B[Validar configuracoes]
    B --> C[Criar Pipeline]
    C --> D[Compilar grafo LangGraph]
    D --> E[Ler Google Sheets]
    E --> F{Ha pacientes com STATUS = 1?}

    F -- Nao --> Z[Finalizar execucao]
    F -- Sim --> G[Abrir browser compartilhado]

    G --> H[Selecionar paciente]
    H --> I[Executar agente browser-use]
    I --> J[Login no Portal HMV se necessario]
    J --> K[Buscar paciente]
    K --> L{Paciente encontrado?}

    L -- Nao --> M[Registrar nao encontrado]
    M --> N[Atualizar STATUS = 0]

    L -- Sim --> O[Ler ID do paciente]
    O --> P[Listar exames alvo]
    P --> Q{Ha exame alvo pendente?}

    Q -- Sim --> R[Abrir exame e relatorio]
    R --> S[Chamar download_exam_report]
    S --> T[Verificar historico e duplicidade]
    T --> U[Ler texto do laudo via CDP]
    U --> V{Ignorado ou indisponivel?}

    V -- Ignorado --> W[Registrar ignorado]
    V -- Indisponivel --> X[Registrar falha/indisponivel]
    V -- Nao --> Y[Extrair PDF: FETCH ou HTML->PDF]
    Y --> AA[Salvar PDF local]
    AA --> AD[Registrar sucesso e historico]

    W --> Q
    X --> Q
    AD --> Q

    Q -- Nao --> AF[Retornar SaidaAgente]
    AF --> AG{Houve falhas reais?}

    AG -- Nao --> AH[Atualizar STATUS = 0]
    AG -- Sim --> AI[Manter STATUS = 1]

    AH --> AJ{Ainda ha pacientes?}
    AI --> AJ
    N --> AJ

    AJ -- Sim --> H
    AJ -- Nao --> Z
    Z --> AK[Fechar browser]
    AK --> AL[Gerar execucao_*.txt e erros_*.json]

Sugestao de legenda:
- Blocos azuis: orquestracao do pipeline.
- Blocos verdes: decisoes e acoes do agente IA.
- Blocos amarelos: Portal HMV.
- Blocos roxos: tool deterministica download_exam_report.
- Blocos vermelhos: falhas, indisponibilidade ou reprocessamento.
- Blocos cinza: persistencia, relatorios e status da planilha.

Tambem gere uma explicacao curta para acompanhar a figura no artigo, com 1 ou 2
paragrafos, destacando a separacao entre navegacao agentica e operacoes
deterministicas.
```

## Legenda curta para acompanhar a figura

O fluxo representa um pipeline agentico no qual o LangGraph organiza o lote de
pacientes, o agente browser-use navega no portal HMV e a tool
`download_exam_report` executa as etapas criticas de captura, validacao e
registro dos laudos. A separacao entre navegacao agentica e operacoes
deterministicas permite combinar flexibilidade de interface com maior controle
sobre download local, historico e relatorios.
