"""Filtros puros de exame — sem dependência de browser, unit-testáveis."""
from app.core.config import (
    EXAM_YEAR_CUTOFF,
    EXAM_YEAR_MAX,
    EXAM_TARGET_KEYWORDS,
    EXAM_EXCLUDE_KEYWORDS,
    EXAM_REPORT_EXCLUDE_MARKERS,
)
from app.domain.history import remove_accents


def check_exam_date(date_str: str) -> bool:
    """True se o ano do exame estiver na janela configurada. Formato esperado:
    'DD/MM/YYYY ...' (hora opcional)."""
    try:
        ano = int(date_str.split(" ")[0].split("/")[2])
        return EXAM_YEAR_CUTOFF <= ano <= EXAM_YEAR_MAX
    except (ValueError, IndexError, AttributeError):
        return False


def is_relevant_exam(exam_text: str) -> bool:
    """True se o nome do exame casar com as keywords de mama e NÃO for um
    exame excluído (localização pré-cirúrgica etc.)."""
    normalized = remove_accents(exam_text).upper()
    if any(excl in normalized for excl in EXAM_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in normalized for keyword in EXAM_TARGET_KEYWORDS)


def texto_indica_skip(texto: str) -> bool:
    """True se o TEXTO DO LAUDO contém marcadores de carta de procedimento
    (não é exame diagnóstico — não salvar como laudo baixado)."""
    markers = [remove_accents(m).upper() for m in EXAM_REPORT_EXCLUDE_MARKERS]
    blob = remove_accents(texto).upper()
    return any(marker in blob for marker in markers)
