"""Filtros determinísticos do RPA — sem dependência de browser."""
import re
from datetime import datetime
from difflib import SequenceMatcher

from app.core.config import (
    EXAM_YEAR_CUTOFF,
    EXAM_YEAR_MAX,
    EXAM_TARGET_KEYWORDS,
    EXAM_EXCLUDE_KEYWORDS,
    EXAM_REPORT_EXCLUDE_MARKERS,
    EXAM_MODALIDADES_PROIBIDAS,
    EXAM_PROCEDIMENTOS_PROIBIDOS,
    EXAM_REPORT_RM_MARKERS,
    EXAM_REPORT_HEADER_DELIM,
    EXAM_REPORT_HEADER_MAX,
    DEDUP_SIMILARIDADE,
    DEDUP_JANELA_DIAS,
)
from app.domain.history import remove_accents


def check_exam_date(date_str: str) -> bool:
    """True se o ano do exame estiver na janela configurada. Formato esperado:
    'DD/MM/YYYY ...' (hora opcional)."""
    date = parse_exam_date(date_str)
    return bool(date and EXAM_YEAR_CUTOFF <= date.year <= EXAM_YEAR_MAX)


def is_relevant_exam(exam_text: str) -> bool:
    """True se o nome do exame casar com as keywords de mama e NÃO for um
    exame excluído (localização pré-cirúrgica etc.)."""
    normalized = remove_accents(exam_text).upper()
    if any(excl in normalized for excl in EXAM_EXCLUDE_KEYWORDS):
        return False
    if re.search(EXAM_MODALIDADES_PROIBIDAS, normalized):
        return False
    if re.search(EXAM_PROCEDIMENTOS_PROIBIDOS, normalized):
        return False
    return any(keyword in normalized for keyword in EXAM_TARGET_KEYWORDS)


def texto_indica_skip(texto: str) -> bool:
    """True se o TEXTO DO LAUDO contém marcadores de carta de procedimento
    (não é exame diagnóstico — não salvar como laudo baixado)."""
    markers = [remove_accents(m).upper() for m in EXAM_REPORT_EXCLUDE_MARKERS]
    blob = remove_accents(texto).upper()
    return any(marker in blob for marker in markers)


def extract_report_title(texto: str) -> str:
    """Obtém a parte inicial do laudo usada pelo árbitro de cartas."""
    lines = [line.strip() for line in (texto or "").splitlines() if line.strip()]
    return " ".join(lines[:12])[:EXAM_REPORT_HEADER_MAX]


def laudo_tem_titulo_valido(texto: str) -> bool:
    """Uma saudação no corpo só barra quando o título não é exame diagnóstico."""
    return is_relevant_exam(extract_report_title(texto))


def laudo_tem_ressonancia(texto: str) -> bool:
    header = remove_accents(texto or "").upper()[:EXAM_REPORT_HEADER_MAX]
    if EXAM_REPORT_HEADER_DELIM in header:
        header = header.split(EXAM_REPORT_HEADER_DELIM, 1)[0]
    return any(remove_accents(marker).upper() in header for marker in EXAM_REPORT_RM_MARKERS)


def parse_exam_date(date_str: str):
    match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", date_str or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%d/%m/%Y").date()
    except ValueError:
        return None


def report_similarity(left: str, right: str) -> float:
    a = " ".join(remove_accents(left or "").upper().split())
    b = " ".join(remove_accents(right or "").upper().split())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def is_duplicate_report(texto: str, data_exame: str, anteriores: list[dict]) -> tuple[bool, float]:
    current_date = parse_exam_date(data_exame)
    best = 0.0
    for previous in anteriores:
        previous_date = parse_exam_date(previous.get("data_exame", ""))
        if current_date and previous_date and abs((current_date - previous_date).days) > DEDUP_JANELA_DIAS:
            continue
        ratio = report_similarity(texto, previous.get("texto", ""))
        best = max(best, ratio)
        if ratio >= DEDUP_SIMILARIDADE:
            return True, ratio
    return False, best
