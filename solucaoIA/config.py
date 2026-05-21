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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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
AGENT_ONLY_MODE = os.getenv("AGENT_ONLY_MODE", "true").lower() == "true"

# IA: Escolher entre "gemini" (cloud) ou "local" (Ollama/LM Studio)
AI_PROVIDER = os.getenv("AI_PROVIDER", "local").lower()  # "gemini" ou "local"

# Para Gemini (cloud)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Para IA Local (Ollama ou LM Studio)
# Ollama: http://localhost:11434/v1
# LM Studio: http://localhost:1234/v1
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "gemma2:2b")  # Nome do modelo (ex: gemma2, mistral, llama2)
LOCAL_LLM_TIMEOUT = int(os.getenv("LOCAL_LLM_TIMEOUT", "300"))
LOCAL_AGENT_STEP_TIMEOUT = int(os.getenv("LOCAL_AGENT_STEP_TIMEOUT", "300"))
LOCAL_USE_VISION = os.getenv("LOCAL_USE_VISION", "false").lower() == "true"

