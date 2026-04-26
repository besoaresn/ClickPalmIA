# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mantendo para garantir que o robô funcione em qualquer lugar (PC ou Servidor)
IS_DOCKER = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER', 'false').lower() == 'true'
HEADLESS_MODE = os.getenv('HEADLESS', str(IS_DOCKER)).lower() == 'true'

SITE_URL = "https://portalpacientesexames.hmv.org.br/portal/WebLogin.aspx?force_all_browsers=truebr/"
USER = os.getenv("PORTAL_USER", "")
PASS = os.getenv("PORTAL_PASS", "")

# Seletores Essenciais
USER_FIELD_SELECTOR = "loginUsernameInput"
PASS_FIELD_SELECTOR = "loginPassword"
LOGIN_BUTTON_SELECTOR = "login-button"
SEARCH_BAR_SELECTOR = "sptGeneralDetailsInput"

# Caminhos
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
HISTORY_FILE = os.path.join(BASE_DIR, "historico_downloads.json")
PENDENTES_IA_FILE = os.path.join(BASE_DIR, "pendentes_ia.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credenciais.json")

# URL do Google Sheets
SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "")

# false = fluxo atual (RPA + IA fallback)
# true  = modo agente-only (sem RPA)
AGENT_ONLY_MODE = os.getenv("AGENT_ONLY_MODE", "false").lower() == "true"