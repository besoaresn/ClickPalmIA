import os
import sys

# Desliga a telemetria anônima do browser-use (precisa vir antes de importá-lo).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_ANONYMOUS_TELEMETRY", "false")

from dotenv import load_dotenv

load_dotenv()

if sys.prefix != sys.base_prefix:
    venv_bin = os.path.join(sys.prefix, "Scripts" if os.name == "nt" else "bin")
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if os.path.isdir(venv_bin) and venv_bin not in path_parts:
        os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)
PROJECT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.abspath(os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data")))

# --- Armazenamento de artefatos ---
# local = comportamento atual; s3 = disco efêmero local + bucket persistente.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_PREFIX = os.getenv("S3_PREFIX", "clickpalmia").strip("/")
S3_REGION = os.getenv("S3_REGION", os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", ""))).strip()
S3_PRESIGNED_URL_EXPIRY = int(os.getenv("S3_PRESIGNED_URL_EXPIRY", "3600"))
# Contrato específico das métricas: somente telemetria e relatórios sobem para
# este prefixo. PDFs permanecem no EFS/disco local por conterem dados de paciente.
RESULTS_S3_URI = os.getenv("RESULTS_S3_URI", "").strip().rstrip("/")

# --- Execução ---
IS_DOCKER = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER', 'false').lower() == 'true'
HEADLESS_MODE = os.getenv('HEADLESS', str(IS_DOCKER)).lower() == 'true'

# --- Portal HMV (login feito pelo agente) ---
SITE_URL = "https://portalpacientesexames.hmv.org.br/portal/WebLogin.aspx?force_all_browsers=truebr/"
USER = os.getenv("PORTAL_USER", "")
PASS = os.getenv("PORTAL_PASS", "")

# Seletores do portal (usados pelo agente como dica e por checagens determinísticas)
USER_FIELD_SELECTOR = "loginUsernameInput"
PASS_FIELD_SELECTOR = "loginPassword"
LOGIN_BUTTON_SELECTOR = "login-button"
SEARCH_BAR_SELECTOR = "sptGeneralDetailsInput"

# --- LLM ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
# Segunda chave deve pertencer a outro projeto Google para ter quota independente.
GEMINI_FALLBACK_API_KEY = os.getenv("GEMINI_FALLBACK_API_KEY", "")
# Mantém o mesmo modelo por padrão para que a telemetria use o preço do
# Gemini 3.1 Flash-Lite nas duas chaves.
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")

# AWS Bedrock / Claude
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK_FALLBACK_MODEL = os.getenv("BEDROCK_FALLBACK_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK_MAX_TOKENS = int(os.getenv("BEDROCK_MAX_TOKENS", "8192"))
BEDROCK_RETRY_ATTEMPTS = int(os.getenv("BEDROCK_RETRY_ATTEMPTS", "3"))
BEDROCK_AUTH_MODE = os.getenv("BEDROCK_AUTH_MODE", "default").strip().lower()
BEDROCK_API_KEY = os.getenv("BEDROCK_API_KEY", os.getenv("AWS_BEARER_TOKEN_BEDROCK", ""))
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", ""))
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "")

# --- Google Sheets ---
SHEET_URL = os.getenv("SHEET_URL", os.getenv("GOOGLE_SHEET_URL", ""))
CREDENTIALS_FILE = os.path.abspath(os.getenv("CREDENTIALS_FILE", os.path.join(BASE_DIR, "credenciais.json")))

# --- Caminhos de dados (persistentes) ---
DOWNLOAD_DIR = os.path.abspath(os.getenv("DOWNLOAD_DIR", os.path.join(DATA_DIR, "downloads")))
HISTORY_FILE = os.path.abspath(os.getenv("HISTORY_FILE", os.path.join(DATA_DIR, "historico_downloads.json")))
REPORTS_DIR = os.path.abspath(os.getenv("REPORTS_DIR", os.path.join(DATA_DIR, "reports")))

# --- Métricas / telemetria ---
METRICS_DIR = os.path.abspath(os.getenv("METRICS_DIR", os.path.join(DATA_DIR, "metricas")))
TELEMETRY_DIR = os.path.abspath(os.getenv("TELEMETRY_DIR", os.path.join(METRICS_DIR, "telemetria")))
METRICS_REFINED_DIR = os.path.abspath(os.getenv("METRICS_REFINED_DIR", os.path.join(METRICS_DIR, "refinado")))
GABARITO_CSV = os.path.abspath(os.getenv("GABARITO_CSV", os.path.join(METRICS_DIR, "gabarito.csv")))
TERMO_XLSX = os.path.abspath(os.getenv(
    "TERMO_XLSX",
    os.path.join(METRICS_DIR, "termo_consentimento_exames_aprovados_2024_2025.xlsx"),
))

# --- Filtros de exame ---
EXAM_YEAR_CUTOFF = 2024
EXAM_YEAR_MAX = 2025

# Palavras-chave que marcam o exame como alvo (mama).
EXAM_TARGET_KEYWORDS = [
    "MAMA", "MAMO", "MAMMO", "MMG", "BREAST",
    "AXILA", "IMPLANT", "NODULO", "ECOGRAFIA", "ULTRASSONOGRAFIA",
]

# Nomes de exame a ignorar (localização pré-cirúrgica etc.).
EXAM_EXCLUDE_KEYWORDS = [
    "LOCALIZACAO PRE",
    "PRE CIRURGICA",
    "PRE-CIRURGICA",
    "PRE OPERATORIA",
    "PRE-OPERATORIA",
]

# Denylist aplicada antes da lista de palavras-alvo. As fronteiras (\\b) em
# modalidades curtas evitam casar RM dentro de palavras como TERMO.
EXAM_MODALIDADES_PROIBIDAS = (
    r"\bMR\b|\bRM\b|RESSONANCIA|\bTC\b|\bCT\b|TOMOGRAFIA|\bPET\b|"
    r"CINTILOGRAFIA|CINTILO|DENSITOMETRIA"
)
EXAM_PROCEDIMENTOS_PROIBIDOS = (
    r"BIOPSIA|BIOPSY|PUNCAO|DEMARCA|LOCALIZACAO|LOCALIZATION|NEEDLE|GUIAD[AO] POR"
)

# Marcadores no TEXTO DO LAUDO que indicam que NÃO é um exame diagnóstico e não
# deve ser salvo como laudo baixado. O nome do card às vezes engana (diz "MAMO"
# mas o conteúdo é uma carta de procedimento), então a checagem é feita no texto.
#
# "PREZADO(A) COLEGA": validado no portal — laudos com essa saudação são
# cartas de encaminhamento/procedimento (localização pré-op, demarcação,
# biópsia), nunca o laudo diagnóstico. Os laudos diagnósticos reais NÃO trazem
# essa saudação. NÃO remover sem revalidar.
EXAM_REPORT_EXCLUDE_MARKERS = [
    "LOCALIZACAO PRE-OPERATORIA",
    "LOCALIZACAO PRE OPERATORIA",
    "PREZADO(A) COLEGA",
]
EXAM_REPORT_RM_MARKERS = ["RESSONANCIA MAGNETICA", "RM DE MAMA"]
EXAM_REPORT_HEADER_DELIM = "INFORMACAO CLINICA"
EXAM_REPORT_HEADER_MAX = 400

# Deduplicação de um mesmo laudo apresentado em vários cards.
DEDUP_SIMILARIDADE = float(os.getenv("DEDUP_SIMILARIDADE", "0.90"))
DEDUP_JANELA_DIAS = int(os.getenv("DEDUP_JANELA_DIAS", "7"))
DEDUP_LOG_RATIO_MIN = float(os.getenv("DEDUP_LOG_RATIO_MIN", "0.85"))

# --- Custo (infra Fargate + LLM), ver docs/Deploy_AWS_Metricas_Custo_RPA_vs_APA.docx ---
# Tamanho da Task ECS Fargate desta execução (mesmo valor para RPA e APA na comparação).
INFRA_VCPU = float(os.getenv("INFRA_VCPU", "1.0"))
INFRA_MEMORIA_GB = float(os.getenv("INFRA_MEMORIA_GB", "2.0"))
# Preços Fargate (US East, por hora). Ajustar se mudar de região.
INFRA_CUSTO_VCPU_HORA = float(os.getenv("INFRA_CUSTO_VCPU_HORA", "0.04048"))
INFRA_CUSTO_MEMORIA_GB_HORA = float(os.getenv("INFRA_CUSTO_MEMORIA_GB_HORA", "0.004445"))
# Preço padrão do Gemini 3.1 Flash-Lite, por milhão de tokens (USD).
LLM_PRECO_MILHAO_ENTRADA = float(os.getenv("LLM_PRECO_MILHAO_ENTRADA", "0.25"))
LLM_PRECO_MILHAO_SAIDA = float(os.getenv("LLM_PRECO_MILHAO_SAIDA", "1.50"))

# --- Timeouts ---
SEARCH_TIMEOUT = 10.0            # teto (s) para localizar o paciente na tabela
SEARCH_NOT_FOUND_GRACE = 2.0     # tempo (s) antes de confiar no badge "(0)" = sem resultado
STUDY_WAIT_TIMEOUT = 8000        # ms para os cards de exame aparecerem
LAUDO_WAIT_TIMEOUT = 4.0         # teto (s) para o laudo atualizar/estabilizar
REPORT_POPUP_TIMEOUT = 5.0       # teto (s) para o iframe do relatório aparecer no popup
