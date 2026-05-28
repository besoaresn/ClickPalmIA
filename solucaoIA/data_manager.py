import os
import json
import unicodedata
from config import HISTORY_FILE, PENDENTES_IA_FILE, ERROS_AGENTE_FILE


def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', str(input_str))
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def normalize_name(name: str) -> str:
    if not name: return ""
    return " ".join(remove_accents(name).split()).strip().rstrip(".").lower()

#HISTÓRICO DE SUCESSO (ID ANTIGO/VISUAL)
def read_download_history():
    if not os.path.exists(HISTORY_FILE): return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def write_download_history(exam_history_id):
    history = read_download_history()
    if exam_history_id not in history:
        history.append(exam_history_id)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(history, f, indent=4, ensure_ascii=False)

# FILA DE ERROS PARA A IA (DEAD LETTER QUEUE)
def read_pendentes_ia():
    if not os.path.exists(PENDENTES_IA_FILE): return []
    try:
        with open(PENDENTES_IA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def write_pendente_ia(dados_falha):
    lista = read_pendentes_ia()
    # Adiciona apenas se não for duplicado
    if not any(item.get("exam_history_id") == dados_falha.get("exam_history_id") for item in lista):
        lista.append(dados_falha)
        with open(PENDENTES_IA_FILE, 'w', encoding='utf-8') as f: json.dump(lista, f, indent=4, ensure_ascii=False)

def remove_pendente_ia(exam_history_id):
    lista = read_pendentes_ia()
    nova_lista = [item for item in lista if item.get("exam_history_id") != exam_history_id]
    with open(PENDENTES_IA_FILE, 'w', encoding='utf-8') as f: json.dump(nova_lista, f, indent=4, ensure_ascii=False)


def clear_pendentes_ia():
    with open(PENDENTES_IA_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, indent=4, ensure_ascii=False)


def write_erro_agente(dados_erro):
    """Registra erros do agente em arquivo JSON."""
    erros = read_erros_agente()

    if not any(item.get("exam_history_id") == dados_erro.get("exam_history_id") for item in erros):
        erros.append(dados_erro)
        with open(ERROS_AGENTE_FILE, 'w', encoding='utf-8') as f:
            json.dump(erros, f, indent=4, ensure_ascii=False)


def read_erros_agente():
    """Lê erros do agente."""
    if not os.path.exists(ERROS_AGENTE_FILE):
        return []
    try:
        with open(ERROS_AGENTE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def clear_erros_agente():
    """Limpa arquivo de erros."""
    with open(ERROS_AGENTE_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, indent=4, ensure_ascii=False)

def seed_pendentes_ia_from_patients(pacientes):
    """
    Cria uma pendência sintética por paciente para permitir execução agente-only
    sem depender de falha prévia do RPA.
    """
    lista = []
    history = read_download_history()

    for p in pacientes:
        nome = str(p.get("nome", "")).strip()
        cpf = str(p.get("cpf", "")).strip()
        if not nome:
            continue

        data_exame = p.get("data_exame", "N/A")
        exam_history_id = f"AGENTONLY-{remove_accents(nome)}-{cpf}-{data_exame}"

        if exam_history_id in history:
            print(f"    [SKIP] Paciente {nome} - {data_exame} já foi processado. Ignorando...")
            continue

        lista.append({
            "nome": nome,
            "cpf": cpf,
            "exam_history_id": exam_history_id,
            "data_exame": data_exame,
            "nome_exame": "BUSCA_POR_EXAMES_DE_MAMA (MAMA, MAMO, MAMMO, MMG, BREAST, AXILA, IMPLANT, NODULO, ECOGRAFIA, ULTRASSONOGRAFIA)"
        })

    with open(PENDENTES_IA_FILE, 'w', encoding='utf-8') as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)

    return len(lista)
