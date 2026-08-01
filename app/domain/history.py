import os
import json
import unicodedata

from app.core.config import HISTORY_FILE
from app.integrations.storage import get_storage

HISTORY_S3_KEY = "history/historico_downloads.json"


def remove_accents(input_str):
    if not input_str:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', str(input_str))
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def normalize_name(name: str) -> str:
    if not name:
        return ""
    return " ".join(remove_accents(name).split()).strip().rstrip(".").lower()


def read_download_history():
    storage = get_storage()
    if storage.enabled:
        history = storage.read_json(HISTORY_S3_KEY, HISTORY_FILE, [])
        return history if isinstance(history, list) else []
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def write_download_history(exam_history_id):
    history = read_download_history()
    if exam_history_id not in history:
        history.append(exam_history_id)
        storage = get_storage()
        if storage.enabled:
            storage.write_json(history, HISTORY_S3_KEY, HISTORY_FILE)
        else:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=4, ensure_ascii=False)
