"""Testes puros dos filtros de exame (sem browser)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.filters import check_exam_date, is_relevant_exam, texto_indica_skip


def test_check_exam_date_corte_2024():
    assert check_exam_date("15/03/2024 10:30") is True
    assert check_exam_date("01/01/2025") is True
    assert check_exam_date("01/01/2026") is False
    assert check_exam_date("31/12/2023 09:00") is False
    assert check_exam_date("data oculta") is False
    assert check_exam_date("") is False


def test_is_relevant_exam_keywords_mama():
    assert is_relevant_exam("MAMOGRAFIA BILATERAL") is True
    assert is_relevant_exam("US MAMARIA") is True
    assert is_relevant_exam("Ecografia de mama direita") is True
    assert is_relevant_exam("RAIO-X DE TORAX") is False
    assert is_relevant_exam("TOMOGRAFIA DE CRANIO") is False


def test_is_relevant_exam_exclui_pre_cirurgica():
    # Mesmo contendo "MAMO", localização pré-cirúrgica é excluída pelo nome.
    assert is_relevant_exam("MAMOGRAFIA LOCALIZACAO PRE-CIRURGICA") is False
    assert is_relevant_exam("MAMA PRE OPERATORIA") is False


def test_texto_indica_skip_carta_procedimento():
    assert texto_indica_skip("Prezado(a) Colega, encaminho a paciente...") is True
    assert texto_indica_skip("LOCALIZACAO PRE-OPERATORIA da lesao") is True
    assert texto_indica_skip("Mamografia: BI-RADS 2. Achados benignos.") is False
