import os

# Desliga a telemetria anônima do browser-use (precisa vir antes de importá-lo).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_ANONYMOUS_TELEMETRY", "false")

from dotenv import load_dotenv

load_dotenv()

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.abspath(os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data")))

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

# --- LLM (Gemini) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# --- Google Sheets ---
SHEET_URL = os.getenv("SHEET_URL", os.getenv("GOOGLE_SHEET_URL", ""))
CREDENTIALS_FILE = os.path.abspath(os.getenv("CREDENTIALS_FILE", os.path.join(BASE_DIR, "credenciais.json")))

# --- Caminhos de dados (persistentes) ---
DOWNLOAD_DIR = os.path.abspath(os.getenv("DOWNLOAD_DIR", os.path.join(DATA_DIR, "downloads")))
HISTORY_FILE = os.path.abspath(os.getenv("HISTORY_FILE", os.path.join(DATA_DIR, "historico_downloads.json")))
REPORTS_DIR = os.path.abspath(os.getenv("REPORTS_DIR", os.path.join(DATA_DIR, "reports")))

# --- Filtros de exame ---
EXAM_YEAR_CUTOFF = 2024

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

# Marcadores no TEXTO DO LAUDO que indicam que NÃO é um exame diagnóstico e
# não deve ser enviado para a API. O nome do card às vezes engana (diz "MAMO"
# mas o laudo é uma carta de procedimento), então a checagem é feita no texto.
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

# --- Timeouts ---
SEARCH_TIMEOUT = 10.0            # teto (s) para localizar o paciente na tabela
SEARCH_NOT_FOUND_GRACE = 2.0     # tempo (s) antes de confiar no badge "(0)" = sem resultado
STUDY_WAIT_TIMEOUT = 8000        # ms para os cards de exame aparecerem
LAUDO_WAIT_TIMEOUT = 4.0         # teto (s) para o laudo atualizar/estabilizar
REPORT_POPUP_TIMEOUT = 5.0       # teto (s) para o iframe do relatório aparecer no popup
