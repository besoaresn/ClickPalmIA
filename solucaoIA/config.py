# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SITE_URL = "https://portalpacientesexames.hmv.org.br/portal/WebLogin.aspx?force_all_browsers=truebr/"
USER = os.getenv("PORTAL_USER", "")
PASS = os.getenv("PORTAL_PASS", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# Caminhos
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
HISTORY_FILE = os.path.join(BASE_DIR, "historico_downloads.json")
PENDENTES_IA_FILE = os.path.join(BASE_DIR, "pendentes_ia.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credenciais.json")
ERROS_AGENTE_FILE = os.path.join(BASE_DIR, "erros_agente.json")

# URL do Google Sheets
SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "")
