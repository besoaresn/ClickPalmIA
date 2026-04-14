# RPA Híbrido com Agente de IA (Browser Use + Playwright)

Um pipeline de extração de dados resiliente que supera os obstáculos da automação tradicional. Este projeto combina a velocidade e previsibilidade da automação programática (**Playwright**) com a adaptabilidade e inteligência de Agentes Autônomos (**Browser Use / LLMs**).

Dessa forma, o sistema evita problemas recorrentes do RPA tradicional — como lentidão de servidor, pop-ups inesperados, mudanças de layout e renderização de iframes —, garantindo uma taxa de sucesso próxima a 100% através de uma arquitetura de **Dead Letter Queue (Fila de Falhas)**.

---

## Arquitetura do Projeto

O sistema foi desenhado sob o princípio de Separação de Responsabilidades (Modularização) e Processamento Stateless (Sem Estado). Ele se divide em duas fases principais:

1. **Fase 1: O Motor RPA (Rápido e Determinístico)**
   O Playwright acessa o portal, busca o paciente, abre o histórico e tenta baixar os exames de imagem via injeção de scripts e interceptação de `iframes`. Se um exame falha (timeout, tela branca, erro no site), o robô não trava: ele apenas anota as características desse exame em um JSON (Fila de Erros) e segue em frente.

2. **Fase 2: A Equipe de Resgate (Inteligência Artificial)**
   Após o RPA varrer todos os pacientes, o `main.py` aciona o Agente de IA. O Agente lê a Fila de Erros, acessa o portal "lendo a tela" como um humano, navega até os exames específicos que o RPA não conseguiu baixar, resolve os imprevistos da interface e realiza o download.

---

## Estrutura de Arquivos (Módulo por Módulo)

O projeto está limpo e modularizado nos seguintes arquivos essenciais:

* **`main.py` (O Orquestrador):**
  Lê a fila de pacientes do Google Sheets (onde `STATUS = 1`). Inicia o loop da Fase 1 (RPA). Ao terminar, dispara a Fase 2 (IA). No final, faz a auditoria: se a fila de erros do paciente estiver vazia, ele atualiza o status na nuvem para `0`.
* **`core.py` (O Operário RPA):**
  Contém o robô Playwright puro. Abre e fecha o navegador *por paciente* (Stateless) para evitar acúmulo de cache e travamentos. Lida com a extração complexa de PDFs dentro de `iframes` e converte visualizadores HTML em PDF.
* **`ai_fallback.py` (O Agente Autônomo):**
  Utiliza a biblioteca `browser-use`. Recebe as pendências, agrupa por paciente, e através de Processamento de Linguagem Natural (LLM), entende a interface do site para buscar e forçar o download apenas do que faltou.
* **`data_manager.py` (O Banco de Dados Local):**
  Centraliza toda a leitura e escrita de JSONs. Gerencia o `historico_downloads.json` (para não baixar exames duplicados) e o `pendentes_ia.json` (A Fila de Mortos / DLQ).
* **`api_client.py` (Integração Backend):**
  Responsável por gerar o token de autenticação e realizar o upload (POST) dos PDFs processados para a API da clínica/sistema de destino.
* **`config.py` (Configurações Globais):**
  Concentra variáveis de ambiente, caminhos de diretórios e os seletores CSS do site, facilitando a manutenção caso o layout mude.

---

## Fluxo de Execução Passo a Passo

1. **Leitura:** O `main.py` consulta a API do Google Sheets e puxa todos os pacientes pendentes.
2. **Processamento em Lote (RPA):** Para cada paciente, o `core.py` faz login, busca o nome e varre a tabela de exames.
3. **Extração & DLQ:** O robô tenta baixar cada exame. Se der sucesso, envia para a API e salva no histórico. Se falhar (ex: botão invisível), adiciona o exame no `pendentes_ia.json`.
4. **Resgate (IA):** O `main.py` encerra o RPA e chama o `ai_fallback.py`. A IA acessa apenas as pendências e trabalha para resgatar os PDFs perdidos.
5. **Checkmate (Sheets):** O `main.py` olha para o JSON de pendências. Se o paciente não está mais lá (a IA limpou), o status no Google Sheets é atualizado para `0`.

---

## Como Configurar e Executar

### Pré-requisitos
* Python 3.10 ou superior.
* `pip install -r requirements.txt` (Instale dependências como `playwright`, `browser-use`, `pandas`, `gspread`, `requests`).
* Instale os navegadores do Playwright rodando: `playwright install`

### Arquivos Sensíveis (Não Inclusos no Repositório)
Você precisará configurar os seguintes arquivos na raiz do projeto:

1. **`credenciais.json`**: Chave da Conta de Serviço do Google Cloud para acessar o Google Sheets.
2. **`.env`**: Arquivo de variáveis de ambiente com os seguintes dados:
   ```env
   # Credenciais do Portal de Exames
   PORTAL_USER=seu_usuario
   PORTAL_PASS=sua_senha
   
   # Credenciais da API de Destino
   CLICKPALM_LOGIN_URL=url_de_auth
   CLICKPALM_UPLOAD_URL=url_de_upload
   CLICKPALM_CPF=seu_cpf
   CLICKPALM_PASS=sua_senha
   
   # Chave da IA (Browser Use / LLM)
   BROWSER_USE_API_KEY=sua_chave_aqui
   
   # Configuração de Execução
   HEADLESS=true